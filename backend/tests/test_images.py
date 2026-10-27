import asyncio
import base64
import copy
import json
import threading
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import Attachment, Charge, MediaJob
from app.providers.chat import ProviderError
from app.providers.images import MockImages, OpenRouterImages
from tests.test_attachments import png, upload
from tests.test_bootstrap import signin


class ControlledImages(MockImages):
    def __init__(self, result: str = "success", delay: float = 0) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result, self.delay = result, delay

    async def generate(self, payload, accepted):
        self.calls.append(copy.deepcopy(payload))
        accepted("synthetic-image-generation")
        await asyncio.sleep(self.delay)
        if self.result == "unknown":
            raise ProviderError("submission_unknown")
        data = {"b64_json": base64.b64encode(png()).decode(), "media_type": "image/png"}
        if self.result == "url":
            data = {"url": "http://169.254.169.254/private"}
        elif self.result == "svg":
            data = {
                "b64_json": base64.b64encode(b"<svg><script/></svg>").decode(),
                "media_type": "image/svg+xml",
            }
        elif self.result == "mime":
            data["media_type"] = "image/jpeg"
        elif self.result == "oversized":
            data = {"b64_json": "x" * 100000, "media_type": "image/png"}
        return {
            "data": [data for _ in range(payload.get("n", 1))],
            **(
                {}
                if self.result == "missing_usage"
                else {
                    "usage": {
                        "cost": "0.0005",
                        "prompt_tokens": 12,
                        "completion_tokens": 8,
                        "total_tokens": 20,
                        "secret": "never expose",
                    }
                }
            ),
        }


def body(**updates):
    return {
        "model_id": "mock/image-studio",
        "provider_tag": "local",
        "prompt": "Synthetic raster fixture",
        "options": {"resolution": "512", "aspect_ratio": "1:1", "output_format": "png"},
        "idempotency_key": uuid4().hex,
        **updates,
    }


def finish(client: TestClient, identifier: str) -> dict[str, Any]:
    for _ in range(200):
        response = client.get(f"/api/images/jobs/{identifier}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] not in {"queued", "submitting", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError("Image job did not settle")


def test_dedicated_contract_has_no_post_retry_or_redirect_following(
    settings_factory: Callable[..., Settings],
) -> None:
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.host == "openrouter.ai"
        if request.url.path == "/api/v1/key":
            return httpx.Response(200, json={"data": {"is_management_key": False, "limit": 1}})
        if request.method == "GET" and request.url.path == "/api/v1/images/models":
            return httpx.Response(200, json={"data": []})
        if request.method == "GET":
            return httpx.Response(200, json={"id": "synthetic/image", "endpoints": []})
        return httpx.Response(302, headers={"Location": "https://attacker.invalid/image"})

    async def run():
        provider = OpenRouterImages(
            settings_factory(openrouter_api_key=SecretStr("synthetic-key")),
            httpx.MockTransport(handler),
        )
        await provider.authorize()
        assert await provider.catalog() == []
        assert await provider.endpoints("synthetic/image") == []
        with pytest.raises(ProviderError):
            await provider.generate(
                {"model": "synthetic/image", "prompt": "fixture"}, lambda _: None
            )
        await provider.close()

    asyncio.run(run())
    assert sum(request.method == "POST" for request in seen) == 1
    assert all(request.headers["Authorization"] == "Bearer synthetic-key" for request in seen)
    assert json.loads(seen[-1].content) == {"model": "synthetic/image", "prompt": "fixture"}


def test_image_assets_persist_and_idempotency_never_dispatches_again(
    settings_factory: Callable[..., Settings],
) -> None:
    config, provider = settings_factory(), ControlledImages()
    app = create_app(config, image_provider=provider)
    request = body(count=2)
    with TestClient(app) as client:
        headers = signin(client)
        assert client.post("/api/images/jobs", json=request).status_code == 403
        assert not provider.calls
        quote = client.post(
            "/api/images/quote",
            headers=headers,
            json={key: value for key, value in request.items() if key != "idempotency_key"},
        ).json()
        assert quote["estimated_microusd"] == 2000 and quote["ready"]
        response = client.post("/api/images/jobs", headers=headers, json=request)
        assert response.status_code == 202, response.text
        job = finish(client, response.json()["id"])
        assert job["status"] == "succeeded" and len(job["assets"]) == 2
        assert job["actual_microusd"] == 500 and "secret" not in job["usage"]
        assert job["queue_delay_ms"] >= 0 and job["elapsed_ms"] >= 0
        assert (
            client.post("/api/images/jobs", headers=headers, json=request).json()["id"] == job["id"]
        )
        assert len(provider.calls) == 1
        image_id = job["assets"][0]["id"]
        download = client.get(f"/api/media/{image_id}?download=true")
        assert download.status_code == 200 and download.headers["content-type"] == "image/webp"
        assert "attachment" in download.headers["content-disposition"]
        assert (
            client.get(f"/api/media/{image_id}", headers={"Range": "bytes=0-15"}).status_code == 206
        )
        assert (
            client.post(
                "/api/images/jobs", headers=headers, json={**request, "prompt": "different"}
            ).status_code
            == 409
        )
        assert provider.calls[0]["provider"] == {"only": ["local"], "allow_fallbacks": False}
    with TestClient(create_app(config, image_provider=provider)) as client:
        signin(client)
        assert client.get(f"/api/images/jobs/{job['id']}").json()["status"] == "succeeded"
        assert client.get(f"/api/media/{image_id}").content == download.content
        assert len(provider.calls) == 1
    with TestClient(create_app(config)) as client:
        for path in [
            "/api/images/models",
            "/api/images/jobs",
            f"/api/images/jobs/{job['id']}",
            f"/api/media/{image_id}",
        ]:
            assert client.get(path).status_code == 401


@pytest.mark.parametrize(
    "updates",
    [
        {"options": {"quality": "high"}},
        {"options": {"output_format": "svg"}},
        {"options": {"resolution": "8K"}},
        {"provider_tag": "unknown"},
        {"model_id": "../key"},
        {"options": {"url": "http://127.0.0.1/private"}},
    ],
)
def test_unknown_capabilities_never_spend(
    updates, settings_factory: Callable[..., Settings]
) -> None:
    provider = ControlledImages()
    with TestClient(create_app(settings_factory(), image_provider=provider)) as client:
        response = client.post("/api/images/jobs", headers=signin(client), json=body(**updates))
        assert response.status_code == 422
        assert not provider.calls
        with Session(client.app.state.auth.engine) as db:
            assert not list(db.scalars(select(Charge)))


@pytest.mark.parametrize("result", ["url", "svg", "mime", "oversized"])
def test_only_bounded_rasters_are_saved(result, settings_factory: Callable[..., Settings]) -> None:
    config = settings_factory(max_media_file_bytes=1024)
    provider = ControlledImages(result)
    with TestClient(create_app(config, image_provider=provider)) as client:
        response = client.post("/api/images/jobs", headers=signin(client), json=body())
        job = finish(client, response.json()["id"])
        assert job["status"] == "failed" and not job["assets"]
        assert job["actual_microusd"] == 500
        assert len(provider.calls) == 1
        assert not list((config.data_dir / "media").iterdir())


def test_missing_usage_and_unknown_submission_keep_reservations(
    settings_factory: Callable[..., Settings],
) -> None:
    for result in ["missing_usage", "unknown"]:
        provider = ControlledImages(result)
        with TestClient(create_app(settings_factory(), image_provider=provider)) as client:
            headers = signin(client)
            started = client.post("/api/images/jobs", headers=headers, json=body()).json()
            job = finish(client, started["id"])
            assert job["accounting_state"] == "uncertain" and job["actual_microusd"] is None
            assert job["generation_id"] == "synthetic-image-generation"
            assert (
                client.get("/api/usage").json()["outstanding_microusd"] >= job["reserved_microusd"]
            )
            retry = body(retry_of=job["id"])
            assert client.post("/api/images/jobs", headers=headers, json=retry).status_code == 409
            retry["acknowledge_duplicate_risk"] = True
            assert client.post("/api/images/jobs", headers=headers, json=retry).status_code == 202
            finish(client, client.get("/api/images/jobs").json()[0]["id"])


def test_restart_does_not_resubmit_started_image_job(
    settings_factory: Callable[..., Settings],
) -> None:
    config, provider = settings_factory(), ControlledImages(delay=10)
    app = create_app(config, image_provider=provider)
    with TestClient(app) as client:
        response = client.post("/api/images/jobs", headers=signin(client), json=body())
        identifier = response.json()["id"]
        for _ in range(100):
            if provider.calls:
                break
            time.sleep(0.01)
        assert len(provider.calls) == 1
    provider.delay = 0
    with TestClient(create_app(config, image_provider=provider)) as client:
        signin(client)
        job = client.get(f"/api/images/jobs/{identifier}").json()
        assert job["status"] == "submission_unknown" and job["accounting_state"] == "uncertain"
        time.sleep(0.05)
        assert len(provider.calls) == 1


def test_image_references_are_forwarded_and_gc_respects_job_references(
    settings_factory: Callable[..., Settings],
) -> None:
    config, provider = settings_factory(), ControlledImages()
    app = create_app(config, image_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        attachment = upload(client, headers, "reference.png", png(), "image/png").json()[0]
        request = body(attachment_ids=[attachment["id"]])
        job = finish(
            client, client.post("/api/images/jobs", headers=headers, json=request).json()["id"]
        )
        image_id = job["assets"][0]["id"]
        assert provider.calls[0]["input_references"][0]["image_url"]["url"].startswith(
            "data:image/webp;base64,"
        )
        assert (
            client.delete(f"/api/attachments/{attachment['id']}", headers=headers).status_code
            == 409
        )
        with Session(app.state.auth.engine) as db:
            item = db.get(Attachment, attachment["id"])
            item.created_at = 1
            db.commit()
        app.state.attachments.collect()
        assert client.get(f"/api/attachments/{attachment['id']}").status_code == 200
        assert client.delete(f"/api/images/jobs/{job['id']}", headers=headers).status_code == 409
        assert (
            client.delete(f"/api/images/jobs/{job['id']}?confirm=true", headers=headers).status_code
            == 204
        )
        assert client.get(f"/api/media/{image_id}").status_code == 404
        assert client.get(f"/api/attachments/{attachment['id']}").status_code == 404
        assert client.post("/api/images/jobs", headers=headers, json=request).status_code == 410
        with Session(app.state.auth.engine) as db:
            assert len(list(db.scalars(select(Charge)))) == 1


def test_unknown_pricing_requires_approved_allowance(
    settings_factory: Callable[..., Settings],
) -> None:
    class TokenPriced(ControlledImages):
        async def endpoints(self, model):
            endpoints = await super().endpoints(model)
            endpoints[0]["pricing"] = [
                {"billable": "output_image", "unit": "token", "cost_usd": "0.00001"}
            ]
            return endpoints

    config = settings_factory(
        provider_mode="openrouter",
        openrouter_api_key=SecretStr("synthetic-key"),
        max_request_usd=Decimal("0.02"),
        daily_budget_usd=Decimal("0.03"),
    )
    from app.providers.chat import MockChat

    with TestClient(
        create_app(config, chat_provider=MockChat(), image_provider=TokenPriced())
    ) as client:
        headers = signin(client)
        assert client.post("/api/images/jobs", headers=headers, json=body()).status_code == 402
    config.image_request_allowance_usd = Decimal("0.02")
    provider = TokenPriced(delay=0.1)
    with TestClient(
        create_app(config, chat_provider=MockChat(), image_provider=provider)
    ) as client:
        headers = signin(client)
        first = client.post("/api/images/jobs", headers=headers, json=body())
        assert first.status_code == 202, first.text
        assert first.json()["uncertain_estimate"] and first.json()["reserved_microusd"] == 20000
        second = client.post("/api/images/jobs", headers=headers, json=body())
        assert second.status_code == 402
        finish(client, first.json()["id"])


def test_restart_recovers_queued_jobs_without_replaying_unknown_submissions(
    settings_factory: Callable[..., Settings],
) -> None:
    config, provider = settings_factory(), ControlledImages()
    app = create_app(config, image_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        app.state.images.schedule = lambda _: None
        queued = client.post("/api/images/jobs", headers=headers, json=body()).json()["id"]
        unknown = client.post("/api/images/jobs", headers=headers, json=body()).json()["id"]
        with Session(app.state.auth.engine) as db:
            job = db.get(MediaJob, unknown)
            job.status = "submitting"
            job.generation_id = "accepted-before-hard-restart"
            db.commit()
    with TestClient(create_app(config, image_provider=provider)) as client:
        signin(client)
        assert finish(client, queued)["status"] == "succeeded"
        job = client.get(f"/api/images/jobs/{unknown}").json()
        assert job["status"] == "submission_unknown"
        assert job["accounting_state"] == "uncertain"
        assert job["generation_id"] == "accepted-before-hard-restart"
        assert len(provider.calls) == 1


def test_image_catalog_keeps_stale_capabilities_and_throttles_refresh(
    settings_factory: Callable[..., Settings],
) -> None:
    from datetime import UTC, datetime, timedelta

    class FailingCatalog(ControlledImages):
        fail = False

        async def catalog(self):
            if self.fail:
                raise ProviderError("provider_read_failed")
            return await super().catalog()

        async def endpoints(self, model):
            if self.fail:
                raise ProviderError("provider_read_failed")
            return await super().endpoints(model)

    now = [datetime(2026, 7, 1, tzinfo=UTC)]
    provider = FailingCatalog()
    with TestClient(
        create_app(settings_factory(), image_provider=provider, clock=lambda: now[0])
    ) as client:
        headers = signin(client)
        assert client.get("/api/images/models").json()["models"][0]["api_family"] == "images"
        first = client.get("/api/images/capabilities", params={"model_id": "mock/image-studio"})
        assert first.status_code == 200
        assert client.post("/api/images/models/refresh", headers=headers).status_code == 429
        provider.fail = True
        now[0] += timedelta(seconds=901)
        assert client.get("/api/images/models").json()["stale"]
        stale = client.get(
            "/api/images/capabilities", params={"model_id": "mock/image-studio"}
        ).json()
        assert stale["stale"] and stale["fetched_at"] == first.json()["fetched_at"]


def test_text_and_image_jobs_share_two_global_generation_slots(
    settings_factory: Callable[..., Settings],
) -> None:
    from app.providers.chat import Chunk, MockChat
    from tests.test_chat import finish as finish_text
    from tests.test_chat import new_conversation, start

    release = threading.Event()

    class Counter:
        active = 0
        maximum = 0

        @classmethod
        async def hold(cls):
            cls.active += 1
            cls.maximum = max(cls.maximum, cls.active)
            while not release.is_set():
                await asyncio.sleep(0.005)
            await asyncio.sleep(0.02)
            cls.active -= 1

    class SharedChat(MockChat):
        async def stream(self, payload):
            await Counter.hold()
            yield Chunk(text="Shared concurrency fixture", usage={"cost": "0"})

    class SharedImages(ControlledImages):
        async def generate(self, payload, accepted):
            await Counter.hold()
            return await super().generate(payload, accepted)

    with TestClient(
        create_app(settings_factory(), chat_provider=SharedChat(), image_provider=SharedImages())
    ) as client:
        headers = signin(client)
        text_jobs = [
            start(client, headers, new_conversation(client, headers)).json()["id"] for _ in range(2)
        ]
        image_jobs = [
            client.post("/api/images/jobs", headers=headers, json=body()).json()["id"]
            for _ in range(2)
        ]
        assert all(
            client.get(f"/api/images/jobs/{identifier}").json()["status"] == "queued"
            for identifier in image_jobs
        )
        release.set()
        for identifier in text_jobs:
            finish_text(client, identifier)
        images = [finish(client, identifier) for identifier in image_jobs]
        assert Counter.maximum == 2
        assert all(job["queue_delay_ms"] >= 0 for job in images)


def test_generated_resolution_is_preserved_under_real_parser_limits(
    settings_factory: Callable[..., Settings],
) -> None:
    class FullSize(ControlledImages):
        async def endpoints(self, model):
            endpoints = await super().endpoints(model)
            endpoints[0]["supported_parameters"]["resolution"]["values"].append("4K")
            return endpoints

        async def generate(self, payload, accepted):
            accepted("synthetic-full-resolution")
            return {
                "data": [
                    {
                        "b64_json": base64.b64encode(png(4096, 4096)).decode(),
                        "media_type": "image/png",
                    }
                ],
                "usage": {"cost": "0.0005"},
            }

    with TestClient(create_app(settings_factory(), image_provider=FullSize())) as client:
        headers = signin(client)
        started = client.post(
            "/api/images/jobs",
            headers=headers,
            json=body(options={"resolution": "4K", "output_format": "png"}),
        )
        job = finish(client, started.json()["id"])
        assert job["status"] == "succeeded", job["error_code"]
        assert (job["assets"][0]["width"], job["assets"][0]["height"]) == (4096, 4096)


def test_expired_media_is_removed_without_losing_accounting(
    settings_factory: Callable[..., Settings],
) -> None:
    from app.models import MediaAsset

    config = settings_factory()
    app = create_app(config, image_provider=ControlledImages())
    with TestClient(app) as client:
        headers = signin(client)
        job = finish(
            client, client.post("/api/images/jobs", headers=headers, json=body()).json()["id"]
        )
        identifier = job["assets"][0]["id"]
        with Session(app.state.auth.engine) as db:
            asset = db.get(MediaAsset, identifier)
            asset.expires_at = 1
            db.commit()
        assert client.get(f"/api/media/{identifier}").status_code == 404
        app.state.images.collect()
        assert not list((config.data_dir / "media").iterdir())
        kept = client.get(f"/api/images/jobs/{job['id']}").json()
        assert not kept["assets"] and kept["actual_microusd"] == 500
