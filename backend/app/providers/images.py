"""Dedicated Image API transport. No chat routing or arbitrary URL retrieval."""

import asyncio
import base64
import io
import json
import re
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Protocol

import httpx
import simplejson
from PIL import Image, ImageDraw

from app.config import Settings
from app.providers.chat import OpenRouter, ProviderError

MODEL_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._:-]*"


class ImageProvider(Protocol):
    async def catalog(self) -> list[dict[str, Any]]: ...
    async def endpoints(self, model: str) -> list[dict[str, Any]]: ...
    async def authorize(self) -> None: ...
    async def generate(
        self, payload: dict[str, Any], accepted: Callable[[str], None]
    ) -> dict[str, Any]: ...
    async def close(self) -> None: ...


class OpenRouterImages:
    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.api = OpenRouter(settings, transport)
        self.api.client.timeout = httpx.Timeout(240, connect=10)

    async def authorize(self) -> None:
        await self.api.authorize()

    async def close(self) -> None:
        await self.api.close()

    async def catalog(self) -> list[dict[str, Any]]:
        await self.authorize()
        raw = await self.api.read_json("images/models", {})
        if not isinstance(raw.get("data"), list):
            raise ProviderError("catalog_invalid")
        return list(raw["data"])

    async def endpoints(self, model: str) -> list[dict[str, Any]]:
        if len(model) > 200 or not re.fullmatch(MODEL_PATTERN, model):
            raise ProviderError("catalog_invalid")
        raw = await self.api.read_json(f"images/models/{model}/endpoints", {})
        if raw.get("id") != model or not isinstance(raw.get("endpoints"), list):
            raise ProviderError("catalog_invalid")
        return list(raw["endpoints"])

    async def generate(
        self, payload: dict[str, Any], accepted: Callable[[str], None]
    ) -> dict[str, Any]:
        try:
            async with self.api.client.stream(
                "POST",
                "images",
                content=simplejson.dumps(payload, use_decimal=True).encode(),
                headers={"Content-Type": "application/json"},
            ) as response:
                identifier = response.headers.get("x-generation-id")
                if identifier and len(identifier) <= 200:
                    accepted(identifier)
                if response.status_code != 200:
                    raise ProviderError(
                        {
                            400: "unsupported_input",
                            401: "provider_auth",
                            402: "provider_credit",
                            429: "provider_rate_limit",
                        }.get(response.status_code, "provider_unavailable")
                    )
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 64 * 1024 * 1024:
                        raise ProviderError("provider_response_limit")
                    content.extend(chunk)
                raw = json.loads(content, parse_float=Decimal)
                if not isinstance(raw, dict) or raw.get("error"):
                    raise ProviderError("provider_invalid_response")
                return raw
        except httpx.HTTPError as exc:
            raise ProviderError("submission_unknown") from exc
        except (ValueError, TypeError) as exc:
            raise ProviderError("provider_invalid_response") from exc


class MockImages:
    async def authorize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "mock/image-studio",
                "name": "Local image studio",
                "architecture": {
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["image"],
                },
            }
        ]

    async def endpoints(self, model: str) -> list[dict[str, Any]]:
        return [
            {
                "provider_name": "Local mock",
                "provider_slug": "local",
                "provider_tag": "local",
                "supported_parameters": {
                    "resolution": {"type": "enum", "values": ["512", "1K"]},
                    "aspect_ratio": {"type": "enum", "values": ["1:1", "16:9", "9:16"]},
                    "output_format": {"type": "enum", "values": ["png", "webp"]},
                    "n": {"type": "range", "min": 1, "max": 4},
                    "input_references": {"type": "boolean"},
                },
                "pricing": [{"billable": "output_image", "unit": "image", "cost_usd": "0.001"}],
            }
        ]

    async def generate(
        self, payload: dict[str, Any], accepted: Callable[[str], None]
    ) -> dict[str, Any]:
        accepted("mock-image-generation")
        await asyncio.sleep(0.1)
        edge = 1024 if payload.get("resolution") == "1K" else 512
        ratio = payload.get("aspect_ratio", "1:1")
        width, height = (
            (edge, edge)
            if ratio == "1:1"
            else ((edge, edge * 9 // 16) if ratio == "16:9" else (edge * 9 // 16, edge))
        )
        image = Image.new("RGB", (width, height), "#325c49")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (24, 24, width - 24, height - 24), radius=18, outline="#d5e2cc", width=3
        )
        draw.text((44, height // 2 - 20), "LOCAL SIMULATION", fill="white", font_size=22)
        draw.text(
            (44, height // 2 + 14),
            "No provider call. No credits spent.",
            fill="white",
            font_size=13,
        )
        output = io.BytesIO()
        image.save(output, format="PNG")
        return {
            "data": [
                {
                    "b64_json": base64.b64encode(output.getvalue()).decode(),
                    "media_type": "image/png",
                }
                for _ in range(payload.get("n", 1))
            ],
            "usage": {"cost": "0", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
