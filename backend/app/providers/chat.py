import asyncio
import json
import time
from collections.abc import AsyncIterator
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

import httpx
import simplejson
from pydantic import BaseModel, Field

from app.config import Settings

BASE_URL = "https://openrouter.ai/api/v1/"


class ProviderError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


class ProviderKeyBudget(BaseModel):
    limit_usd: Decimal = Field(gt=0, allow_inf_nan=False)
    remaining_usd: Decimal = Field(ge=0, allow_inf_nan=False)
    used_usd: Decimal = Field(ge=0, allow_inf_nan=False)
    checked_at: int


class Chunk(BaseModel):
    text: str = ""
    provider: str | None = Field(default=None, max_length=200)
    generation_id: str | None = Field(default=None, max_length=200)
    usage: dict[str, Any] | None = None


class ChatProvider(Protocol):
    async def catalog(self) -> list[dict[str, Any]]: ...
    async def authorize(self) -> None: ...
    async def key_budget(self, refresh: bool = False) -> ProviderKeyBudget: ...
    def stream(self, payload: dict[str, Any]) -> AsyncIterator[Chunk]: ...
    async def close(self) -> None: ...
    async def generation(self, generation_id: str) -> dict[str, Any] | None: ...


class OpenRouter:
    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.authorized_until = 0.0
        self.budget: ProviderKeyBudget | None = None
        self.key_lock = asyncio.Lock()
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            transport=transport,
            headers={"Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}"},
            timeout=httpx.Timeout(90, connect=10),
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_connections=4),
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def read_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            for attempt in range(3):
                async with self.client.stream("GET", path, params=params) as response:
                    if response.status_code in {429, 503} and attempt < 2:
                        value = response.headers.get("Retry-After", "1")
                        try:
                            delay = float(value)
                        except ValueError:
                            try:
                                delay = parsedate_to_datetime(value).timestamp() - time.time()
                            except (ValueError, TypeError, OverflowError):
                                delay = 1
                        await asyncio.sleep(min(10, max(0, delay)))
                        continue
                    if response.status_code != 200:
                        raise ProviderError("provider_read_failed")
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > 8 * 1024 * 1024:
                            raise ProviderError("provider_invalid_response")
                        content.extend(chunk)
                    raw = json.loads(content, parse_float=Decimal)
                    if not isinstance(raw, dict):
                        raise ProviderError("provider_invalid_response")
                    return raw
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("provider_read_failed") from exc
        raise ProviderError("provider_read_failed")

    async def authorize(self) -> None:
        await self._authorize()

    async def key_budget(self, refresh: bool = False) -> ProviderKeyBudget:
        stale = not self.budget or time.time() - self.budget.checked_at >= 15
        await self._authorize(refresh or stale)
        if self.budget is None:
            raise ProviderError("provider_budget_unavailable")
        return self.budget

    async def _authorize(self, refresh: bool = False) -> None:
        async with self.key_lock:
            if not refresh and time.monotonic() < self.authorized_until:
                return
            response = await self.read_json("key", {})
            data = response.get("data")
            if (
                not isinstance(data, dict)
                or data.get("is_management_key") is not False
                or data.get("is_provisioning_key") is True
            ):
                raise ProviderError("provider_key_unrestricted")
            try:
                limit = Decimal(str(data.get("limit")))
                if not limit.is_finite() or limit <= 0:
                    raise ProviderError("provider_key_unrestricted")
            except (ValueError, ArithmeticError) as exc:
                raise ProviderError("provider_key_unrestricted") from exc
            self.budget = None
            try:
                remaining = Decimal(str(data.get("limit_remaining")))
                used = Decimal(str(data.get("usage")))
                if (
                    "limit_reset" not in data
                    or data["limit_reset"] is not None
                    or not remaining.is_finite()
                    or not used.is_finite()
                    or used < 0
                ):
                    raise ValueError("A fixed key budget is required.")
                effective = data.get("effective_budget")
                if isinstance(effective, dict) and effective.get("remaining_usd") is not None:
                    effective_remaining = Decimal(str(effective["remaining_usd"]))
                    if not effective_remaining.is_finite():
                        raise ValueError("Invalid effective budget.")
                    remaining = min(remaining, effective_remaining)
                self.budget = ProviderKeyBudget(
                    limit_usd=limit,
                    remaining_usd=max(Decimal(0), min(limit, remaining)),
                    used_usd=used,
                    checked_at=int(time.time()),
                )
            except (ValueError, ArithmeticError):
                pass
            self.authorized_until = time.monotonic() + 300

    async def catalog(self) -> list[dict[str, Any]]:
        await self.authorize()
        raw = await self.read_json("models", {"output_modalities": "text", "sort": "most-popular"})
        if not isinstance(raw.get("data"), list):
            raise ProviderError("catalog_invalid")
        return list(raw["data"])

    async def generation(self, generation_id: str) -> dict[str, Any] | None:
        raw = await self.read_json("generation", {"id": generation_id})
        value = raw.get("data")
        if not isinstance(value, dict) or value.get("id") != generation_id:
            return None
        return dict(value)

    async def frames(self, response: httpx.Response) -> AsyncIterator[str]:
        pending = bytearray()
        data: list[str] = []
        size = 0
        async for raw in response.aiter_bytes():
            for offset in range(0, len(raw), 4096):
                pending.extend(raw[offset : offset + 4096])
                while b"\n" in pending:
                    line, _, remaining = pending.partition(b"\n")
                    pending = bytearray(remaining)
                    line = line.removesuffix(b"\r")
                    size += len(line)
                    if size > 262144:
                        raise ProviderError("provider_invalid_stream")
                    if line.startswith(b"data:"):
                        data.append(line[5:].lstrip().decode("utf-8"))
                    elif not line:
                        if data:
                            yield "\n".join(data)
                        data, size = [], 0
                if len(pending) + size > 262144:
                    raise ProviderError("provider_invalid_stream")

    async def stream(self, payload: dict[str, Any]) -> AsyncIterator[Chunk]:
        await self.authorize()
        try:
            async with self.client.stream(
                "POST",
                "chat/completions",
                content=simplejson.dumps(payload, use_decimal=True).encode(),
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status_code != 200:
                    raise ProviderError(
                        {
                            401: "provider_auth",
                            402: "provider_credit",
                            429: "provider_rate_limit",
                        }.get(response.status_code, "provider_unavailable")
                    )
                if response.headers.get("x-generation-id"):
                    yield Chunk(generation_id=response.headers["x-generation-id"])
                async for frame in self.frames(response):
                    if frame == "[DONE]":
                        return
                    event = json.loads(frame, parse_float=Decimal)
                    if not isinstance(event, dict) or event.get("error"):
                        raise ProviderError("provider_stream_failed")
                    choices = event.get("choices", [])
                    choice = choices[0] if choices else {}
                    if choice.get("finish_reason") == "error":
                        raise ProviderError("provider_stream_failed")
                    text = choice.get("delta", {}).get("content", "") or ""
                    if not isinstance(text, str):
                        raise ProviderError("provider_invalid_stream")
                    yield Chunk(
                        text=text,
                        provider=event.get("provider"),
                        generation_id=event.get("id"),
                        usage=event.get("usage"),
                    )
                raise ProviderError("provider_interrupted")
        except (
            httpx.HTTPError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            AttributeError,
        ) as exc:
            raise ProviderError("provider_stream_failed") from exc


class MockChat:
    async def key_budget(self, refresh: bool = False) -> ProviderKeyBudget:
        return ProviderKeyBudget(
            limit_usd=Decimal("10"),
            remaining_usd=Decimal("10"),
            used_usd=Decimal(0),
            checked_at=int(time.time()),
        )

    async def authorize(self) -> None:
        pass

    async def generation(self, generation_id: str) -> dict[str, Any] | None:
        return None

    async def close(self) -> None:
        pass

    async def catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "id": f"mock/{slug}",
                "name": f"Local {slug}",
                "context_length": 32000,
                "architecture": {
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                },
                "supported_parameters": ["temperature", "max_tokens"],
                "pricing": {"prompt": "0.0000001", "completion": "0.0000002", "request": "0"},
            }
            for slug in ["steady", "clear", "brief", "deep"]
        ]

    async def stream(self, payload: dict[str, Any]) -> AsyncIterator[Chunk]:
        prompt = payload["messages"][-1]["content"]
        if isinstance(prompt, list):
            prompt = "\n".join(part["text"] for part in prompt if part.get("type") == "text")
        result = (
            f"**Local simulation**\n\n{prompt}\n\n"
            "This is a deterministic mock response. No credits were spent."
        )
        for start in range(0, len(result), 12):
            await asyncio.sleep(0.025)
            yield Chunk(
                text=result[start : start + 12],
                provider="Local mock",
                generation_id="mock-generation",
            )
        yield Chunk(
            usage={
                "prompt_tokens": len(prompt.encode()),
                "completion_tokens": len(result.encode()),
                "cost": "0",
            }
        )
