import asyncio
import json
from collections.abc import AsyncIterator, Callable
from decimal import Decimal

import httpx
import pytest

from app.config import Settings
from app.providers.chat import OpenRouter, ProviderError


class SplitStream(httpx.AsyncByteStream):
    def __init__(self, content: bytes, step: int = 3) -> None:
        self.content, self.step = content, step

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for offset in range(0, len(self.content), self.step):
            yield self.content[offset : offset + self.step]


def with_key(handler):
    def wrapped(request):
        if request.url.path == "/api/v1/key":
            return httpx.Response(200, json={"data": {"is_management_key": False, "limit": 1}})
        return handler(request)

    return wrapped


def test_split_sse_comments_utf8_usage_and_fixed_origin(
    settings_factory: Callable[..., Settings],
) -> None:
    content = (
        ': processing\r\n\r\ndata: {"id":"synthetic-id","provider":"Synthetic",'
        '"choices":[{"delta":{"content":"café"}}]}\r\n\r\n'
        'data: {"choices":[],"usage":{"cost":0.000123}}\n\ndata: [DONE]\n\n'
    ).encode()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "openrouter.ai"
        assert request.url.path == "/api/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer synthetic-key"
        assert json.loads(request.content)["model"] == "synthetic/model"
        return httpx.Response(
            200, stream=SplitStream(content), headers={"X-Generation-Id": "synthetic-id"}
        )

    async def scenario() -> None:
        provider = OpenRouter(
            settings_factory(openrouter_api_key="synthetic-key"),
            httpx.MockTransport(with_key(handler)),
        )
        try:
            chunks = [chunk async for chunk in provider.stream({"model": "synthetic/model"})]
            assert "".join(chunk.text for chunk in chunks) == "café"
            assert chunks[-1].usage["cost"] == Decimal("0.000123")
            assert chunks[0].generation_id == "synthetic-id"
            assert len(calls) == 1
        finally:
            await provider.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "content",
    [
        b'data: {"error":{"message":"private upstream diagnostic"}}\n\n',
        b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
        b"data: " + b"x" * 262145,
    ],
)
def test_post_200_errors_and_unbounded_frames_fail_safely(
    content: bytes, settings_factory: Callable[..., Settings]
) -> None:
    async def scenario() -> None:
        provider = OpenRouter(
            settings_factory(),
            httpx.MockTransport(
                with_key(lambda _: httpx.Response(200, stream=SplitStream(content, 4096)))
            ),
        )
        try:
            with pytest.raises(ProviderError) as captured:
                async for _ in provider.stream({}):
                    pass
            assert "private upstream" not in str(captured.value)
            assert captured.value.code in {
                "provider_stream_failed",
                "provider_interrupted",
                "provider_invalid_stream",
            }
        finally:
            await provider.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "provider_auth"),
        (402, "provider_credit"),
        (429, "provider_rate_limit"),
        (503, "provider_unavailable"),
    ],
)
def test_generation_post_is_never_retried(
    status: int, code: str, settings_factory: Callable[..., Settings]
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json={"error": "private diagnostic"})

    async def scenario() -> None:
        provider = OpenRouter(settings_factory(), httpx.MockTransport(with_key(handler)))
        try:
            with pytest.raises(ProviderError) as captured:
                async for _ in provider.stream({}):
                    pass
            assert captured.value.code == code
            assert len(calls) == 1
        finally:
            await provider.close()

    asyncio.run(scenario())


def test_catalog_reads_honor_retry_after_and_request_explicit_modality(
    settings_factory: Callable[..., Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, delays = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.params["output_modalities"] == "text"
        assert request.url.params["sort"] == "most-popular"
        return (
            httpx.Response(429, headers={"Retry-After": "2"})
            if len(calls) == 1
            else httpx.Response(200, json={"data": []})
        )

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async def scenario() -> None:
        provider = OpenRouter(settings_factory(), httpx.MockTransport(with_key(handler)))
        try:
            assert await provider.catalog() == []
            assert len(calls) == 2 and delays == [2]
        finally:
            await provider.close()

    monkeypatch.setattr(asyncio, "sleep", sleep)
    asyncio.run(scenario())


@pytest.mark.parametrize(
    "data",
    [
        {"is_management_key": True, "limit": 1},
        {"is_management_key": False, "limit": None},
        {"is_management_key": False, "limit": 0},
        {"limit": 1},
    ],
)
def test_unrestricted_or_management_keys_never_dispatch(data, settings_factory):
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={"data": data})

    async def scenario():
        provider = OpenRouter(settings_factory(), httpx.MockTransport(handler))
        try:
            with pytest.raises(ProviderError, match="provider_key_unrestricted"):
                async for _ in provider.stream({}):
                    pass
            assert calls == ["GET"]
        finally:
            await provider.close()

    asyncio.run(scenario())
