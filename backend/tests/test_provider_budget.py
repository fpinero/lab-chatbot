import asyncio
import copy
import time
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.main import create_app
from app.providers.chat import OpenRouter, ProviderError, ProviderKeyBudget
from tests.test_attachments import png, upload
from tests.test_bootstrap import signin
from tests.test_chat import ControlledProvider, finish, new_conversation, start
from tests.test_images import ControlledImages, body
from tests.test_images import finish as finish_image


class BudgetProvider(ControlledProvider):
    def __init__(self, remaining="0.01", **kwargs):
        super().__init__(**kwargs)
        self.remaining = Decimal(remaining)
        self.budget_unavailable = False

    async def key_budget(self, refresh=False):
        if self.budget_unavailable:
            raise ProviderError("provider_read_failed")
        return ProviderKeyBudget(
            limit_usd=Decimal("9.9"),
            remaining_usd=self.remaining,
            used_usd=Decimal("9.9") - self.remaining,
            checked_at=int(time.time()),
        )


def live_settings(settings_factory, **kwargs):
    return settings_factory(
        provider_mode="openrouter",
        spend_control="provider",
        openrouter_api_key=SecretStr("synthetic-key"),
        max_request_usd=0,
        daily_budget_usd=0,
        live_test_budget_usd=0,
        image_request_allowance_usd=0,
        vision_request_allowance_usd=0,
        model_price_ceiling_per_million=0,
        image_price_ceiling_usd=0,
        **kwargs,
    )


def test_provider_budget_replaces_local_caps_and_includes_external_usage(settings_factory):
    provider, images = BudgetProvider(), ControlledImages()
    app = create_app(live_settings(settings_factory), chat_provider=provider, image_provider=images)
    with TestClient(app) as client:
        headers = signin(client)
        usage = client.get("/api/usage").json()
        assert usage["spend_control"] == "provider"
        assert usage["request_limit_microusd"] is usage["daily_limit_microusd"] is None
        assert usage["provider_key_budget"]["remaining_usd"] == "0.01"
        assert usage["provider_key_budget"]["used_usd"] == "9.89"
        assert "synthetic-key" not in str(usage)
        response = start(client, headers, new_conversation(client, headers), verification_run=True)
        assert response.status_code == 202, response.text
        assert finish(client, response.json()["id"])["accounting_state"] == "settled"
        # Settled local costs are already included in the provider remainder.
        provider.remaining = Decimal("0.00005")
        response = start(client, headers, new_conversation(client, headers), max_tokens=32)
        assert response.status_code == 202, response.text
        finish(client, response.json()["id"])
        provider.remaining = Decimal("0")
        response = start(client, headers, new_conversation(client, headers))
        assert (
            response.status_code == 402
            and response.json()["error"]["code"] == "provider_budget_limit"
        )
        assert len(provider.calls) == 2
        assert all("max_price" not in call["provider"] for call in provider.calls)


def test_shared_key_reservations_block_images_and_comparisons(settings_factory):
    provider, images = BudgetProvider("0.0015"), ControlledImages(result="missing_usage")
    app = create_app(live_settings(settings_factory), chat_provider=provider, image_provider=images)
    with TestClient(app) as client:
        headers = signin(client)
        response = client.post(
            "/api/images/jobs", headers=headers, json=body(verification_run=True)
        )
        assert response.status_code == 202, response.text
        assert finish_image(client, response.json()["id"])["accounting_state"] == "uncertain"
        response = client.post("/api/images/jobs", headers=headers, json=body())
        assert response.status_code == 402
        response = client.post(
            "/api/comparisons",
            headers=headers,
            json={
                "conversation_id": new_conversation(client, headers),
                "model_ids": ["mock/steady", "mock/clear"],
                "prompt": "Fixture",
                "max_tokens": 2048,
                "idempotency_key": uuid4().hex,
            },
        )
        assert response.status_code == 402, response.text
        assert len(images.calls) == 1 and not provider.calls
        assert client.get("/api/usage").json()["outstanding_microusd"] == 1000


def test_uncertain_image_pricing_uses_key_remainder_without_modality_allowance(settings_factory):
    class UnknownImages(ControlledImages):
        async def endpoints(self, model):
            endpoints = copy.deepcopy(await super().endpoints(model))
            endpoints[0]["pricing"] = [
                {"billable": "output_image", "unit": "megapixel", "cost_usd": "0.1"}
            ]
            return endpoints

    provider, images = BudgetProvider("0.025"), UnknownImages()
    app = create_app(live_settings(settings_factory), chat_provider=provider, image_provider=images)
    with TestClient(app) as client:
        headers = signin(client)
        quote = client.post(
            "/api/images/quote",
            headers=headers,
            json={k: v for k, v in body().items() if k != "idempotency_key"},
        ).json()
        assert quote["ready"] and quote["spend_control"] == "provider"
        assert quote["uncertain"] and quote["reservation_microusd"] == 25000
        assert not images.calls
        response = client.post("/api/images/jobs", headers=headers, json=body())
        assert response.status_code == 202, response.text
        assert finish_image(client, response.json()["id"])["actual_microusd"] == 500
        provider.remaining = Decimal("0")
        quote = client.post(
            "/api/images/quote",
            headers=headers,
            json={k: v for k, v in body().items() if k != "idempotency_key"},
        ).json()
        assert not quote["ready"] and "remaining OpenRouter" in quote["reason"]


def test_budget_read_failure_never_dispatches(settings_factory):
    provider, images = BudgetProvider(), ControlledImages()
    provider.budget_unavailable = True
    app = create_app(live_settings(settings_factory), chat_provider=provider, image_provider=images)
    with TestClient(app) as client:
        headers = signin(client)
        response = client.post("/api/images/jobs", headers=headers, json=body())
        assert response.status_code == 503
        assert not images.calls


@pytest.mark.parametrize("image_input", [False, True])
def test_uncertain_chat_pricing_reserves_shared_remainder(settings_factory, image_input):
    class UncertainProvider(BudgetProvider):
        async def catalog(self):
            models = await super().catalog()
            if not image_input:
                for model in models:
                    model["pricing"] = {"request": "0.0001"}
            return models

    provider = UncertainProvider("0.02")
    app = create_app(
        live_settings(settings_factory), chat_provider=provider, image_provider=ControlledImages()
    )
    with TestClient(app) as client:
        headers = signin(client)
        attachments = (
            upload(client, headers, "fixture.png", png(), "image/png").json() if image_input else []
        )
        response = start(
            client,
            headers,
            new_conversation(client, headers),
            attachment_ids=[item["id"] for item in attachments],
        )
        assert response.status_code == 202, response.text
        run = finish(client, response.json()["id"])
        assert run["status"] == "succeeded"
        assert run["reserved_microusd"] == 20000
        assert run["settings"]["estimate_kind"] == "provider_key_remainder"
        assert len(provider.calls) == 1 and "max_price" not in provider.calls[0]["provider"]


@pytest.mark.parametrize(
    "changes",
    [
        {"limit_reset": "monthly"},
        {"limit_remaining": None},
        {"limit_remaining": "NaN"},
        {"usage": -1},
        {"is_management_key": True},
        {"limit": None},
    ],
)
def test_provider_mode_requires_readable_fixed_restricted_budget(settings_factory, changes):
    async def run():
        data = {
            "limit": 9.9,
            "limit_remaining": 9.8,
            "usage": 0.1,
            "limit_reset": None,
            "is_management_key": False,
            **changes,
        }
        provider = OpenRouter(
            settings_factory(),
            httpx.MockTransport(lambda _: httpx.Response(200, json={"data": data})),
        )
        try:
            with pytest.raises(ProviderError):
                await provider.key_budget(refresh=True)
        finally:
            await provider.close()

    asyncio.run(run())


def test_provider_budget_refresh_and_effective_remaining(settings_factory):
    async def run():
        data = {
            "limit": 9.9,
            "limit_remaining": 9.8,
            "usage": 0.1,
            "limit_reset": None,
            "is_management_key": False,
            "effective_budget": {"remaining_usd": "1.25"},
        }
        calls = []

        def handler(request):
            assert request.method == "GET" and request.url.path == "/api/v1/key"
            calls.append(request)
            return httpx.Response(200, json={"data": data})

        provider = OpenRouter(settings_factory(), httpx.MockTransport(handler))
        try:
            assert (await provider.key_budget()).remaining_usd == Decimal("1.25")
            assert (await provider.key_budget()).remaining_usd == Decimal("1.25")
            data["effective_budget"]["remaining_usd"] = "0"
            assert (await provider.key_budget(refresh=True)).remaining_usd == 0
            assert len(calls) == 2
        finally:
            await provider.close()

    asyncio.run(run())
