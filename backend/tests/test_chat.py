import asyncio
import time
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import CatalogCache, Charge
from app.providers.chat import Chunk, MockChat, ProviderError
from tests.test_bootstrap import signin


class ControlledProvider(MockChat):
    def __init__(self, missing_usage: bool = False, fail: bool = False, delay: float = 0.05):
        self.calls: list[dict[str, Any]] = []
        self.missing_usage, self.fail, self.delay = missing_usage, fail, delay
        self.catalog_fails = False

    async def catalog(self):
        if self.catalog_fails:
            raise ProviderError("catalog_unavailable")
        return await super().catalog()

    async def stream(self, payload: dict[str, Any]) -> AsyncIterator[Chunk]:
        self.calls.append(payload)
        yield Chunk(
            text="Partial ", provider="Synthetic provider", generation_id="synthetic-generation"
        )
        await asyncio.sleep(self.delay)
        if self.fail:
            raise ProviderError("provider_stream_failed")
        yield Chunk(text="answer")
        if not self.missing_usage:
            yield Chunk(usage={"cost": "0.000123", "prompt_tokens": 5, "completion_tokens": 2})


def new_conversation(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/conversations", headers=headers, json={"title": "Experiment"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def start(client: TestClient, headers: dict[str, str], conversation_id: str, **overrides: Any):
    body = {
        "conversation_id": conversation_id,
        "model_id": "mock/steady",
        "prompt": "Hello",
        "idempotency_key": uuid4().hex,
        "max_tokens": 128,
    }
    body.update(overrides)
    return client.post("/api/runs", headers=headers, json=body)


def finish(client: TestClient, run_id: str) -> dict[str, Any]:
    for _ in range(100):
        value = client.get(f"/api/runs/{run_id}").json()
        if value["status"] in {"succeeded", "failed", "cancelled", "interrupted"}:
            return value
        time.sleep(0.02)
    raise AssertionError("Run did not finish")


def test_snapshot_streaming_usage_and_idempotency(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = ControlledProvider()
    app = create_app(settings_factory(), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        conversation_id = new_conversation(client, headers)
        key = uuid4().hex
        response = start(
            client, headers, conversation_id, idempotency_key=key, system_prompt="Be concise"
        )
        assert response.status_code == 202, response.text
        first = response.json()
        duplicate = start(
            client, headers, conversation_id, idempotency_key=key, system_prompt="Be concise"
        )
        assert duplicate.json()["id"] == first["id"]
        assert (
            start(
                client, headers, conversation_id, idempotency_key=key, prompt="Changed"
            ).status_code
            == 409
        )
        events = client.get(f"/api/runs/{first['id']}/events")
        assert events.headers["content-type"].startswith("text/event-stream")
        assert "event: run.snapshot" in events.text
        ids = [int(line[4:]) for line in events.text.splitlines() if line.startswith("id: ")]
        assert ids == sorted(set(ids))
        result = finish(client, first["id"])
        assert result["output"] == "Partial answer"
        assert result["actual_microusd"] == 123 and result["accounting_state"] == "settled"
        assert len(provider.calls) == 1
        assert provider.calls[0]["messages"] == [
            {"role": "system", "content": "Be concise"},
            {"role": "user", "content": "Hello"},
        ]
        assert "tools" not in provider.calls[0]
        again = start(
            client, headers, conversation_id, model_id="mock/clear", retry_of=first["id"], prompt=""
        )
        assert again.status_code == 202
        finish(client, again.json()["id"])
        assert provider.calls[1]["messages"] == provider.calls[0]["messages"]
        assert provider.calls[1]["model"] == "mock/clear"
        usage = client.get("/api/usage").json()
        assert usage["daily_actual_microusd"] == 246


def test_missing_usage_and_post_200_failure_keep_reservations(
    settings_factory: Callable[..., Settings],
) -> None:
    for fail in [False, True]:
        provider = ControlledProvider(missing_usage=True, fail=fail)
        with TestClient(create_app(settings_factory(), chat_provider=provider)) as client:
            headers = signin(client)
            result = start(client, headers, new_conversation(client, headers))
            answer = finish(client, result.json()["id"])
            assert answer["accounting_state"] == "uncertain" and answer["actual_microusd"] is None
            assert answer["reserved_microusd"] > 0
            assert answer["status"] == ("failed" if fail else "succeeded")
            assert "Partial" in answer["output"]


def test_restart_never_resubmits_running_paid_call(
    settings_factory: Callable[..., Settings],
) -> None:
    config = settings_factory()
    provider = ControlledProvider(delay=30)
    app = create_app(config, chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        result = start(client, headers, new_conversation(client, headers)).json()
        for _ in range(50):
            if provider.calls:
                break
            time.sleep(0.01)
        assert len(provider.calls) == 1
        token = client.cookies[config.cookie_name]
    replacement = ControlledProvider()
    with TestClient(create_app(config, chat_provider=replacement)) as client:
        client.cookies.set(config.cookie_name, token)
        restored = client.get(f"/api/runs/{result['id']}").json()
        assert restored["status"] == "interrupted"
        assert restored["accounting_state"] == "uncertain"
        assert replacement.calls == []


def test_cancel_preserves_partial_and_unknown_billing(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = ControlledProvider(delay=30)
    with TestClient(create_app(settings_factory(), chat_provider=provider)) as client:
        headers = signin(client)
        result = start(client, headers, new_conversation(client, headers)).json()
        time.sleep(0.3)
        response = client.post(f"/api/runs/{result['id']}/cancel", headers=headers)
        assert response.json()["status"] == "cancelled"
        assert response.json()["output"] == "Partial "
        assert response.json()["accounting_state"] == "uncertain"
        assert len(provider.calls) == 1


def test_invalid_models_context_and_unsupported_parameters_never_dispatch(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = ControlledProvider()
    with TestClient(create_app(settings_factory(), chat_provider=provider)) as client:
        headers = signin(client)
        conversation_id = new_conversation(client, headers)
        assert start(client, headers, conversation_id, model_id="unknown").status_code == 422
        assert start(client, headers, conversation_id, max_tokens=9999).status_code == 422
        assert (
            start(
                client, headers, conversation_id, prompt="x" * 23999, system_prompt="y" * 11000
            ).status_code
            == 422
        )
        assert start(client, headers, conversation_id, tools=[{}]).status_code == 422
        assert not provider.calls


def test_catalog_stale_and_refresh_throttle(settings_factory: Callable[..., Settings]) -> None:
    provider = ControlledProvider()
    app = create_app(settings_factory(), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        catalog = client.get("/api/models").json()
        assert len(catalog["models"]) == 2 and catalog["stale"] is False
        assert client.post("/api/models/refresh", headers=headers).status_code == 429
        with Session(app.state.auth.engine) as db:
            cached = db.get(CatalogCache, "chat")
            cached.fetched_at -= 1000
            cached.last_attempt_at -= 1000
            db.commit()
        provider.catalog_fails = True
        stale = client.get("/api/models").json()
        assert stale["stale"] is True and stale["models"] == catalog["models"]


def test_history_export_deletion_and_idempotency_tombstone(
    settings_factory: Callable[..., Settings],
) -> None:
    with TestClient(
        create_app(settings_factory(), chat_provider=ControlledProvider(delay=0))
    ) as client:
        headers = signin(client)
        conversation_id = new_conversation(client, headers)
        key = uuid4().hex
        result = start(client, headers, conversation_id, idempotency_key=key).json()
        finish(client, result["id"])
        assert (
            client.patch(
                f"/api/conversations/{conversation_id}",
                headers=headers,
                json={"title": "Renamed experiment"},
            ).status_code
            == 200
        )
        assert client.get("/api/conversations?q=Renamed").json()[0]["id"] == conversation_id
        export = client.get(f"/api/conversations/{conversation_id}/export?format=json")
        assert export.json()["runs"][0]["output"] == "Partial answer"
        assert "attachment" in export.headers["content-disposition"]
        assert (
            client.delete(f"/api/conversations/{conversation_id}", headers=headers).status_code
            == 409
        )
        assert (
            client.delete(
                f"/api/conversations/{conversation_id}?confirm=true", headers=headers
            ).status_code
            == 204
        )
        assert client.get(f"/api/runs/{result['id']}").status_code == 404
        assert start(client, headers, conversation_id, idempotency_key=key).status_code == 410
        assert client.get("/api/usage").json()["daily_actual_microusd"] == 123


def test_transactional_budget_reservations_block_concurrent_overspend(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = ControlledProvider(delay=30)
    config = settings_factory(
        provider_mode="openrouter",
        openrouter_api_key="synthetic-key",
        max_request_usd="0.01",
        daily_budget_usd="0.0001",
    )
    app = create_app(config, chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        first = new_conversation(client, headers)
        second = new_conversation(client, headers)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(start, client, headers, identifier)
                for identifier in [first, second]
            ]
            results = [future.result() for future in futures]
        assert sorted(result.status_code for result in results) == [202, 402]
        with Session(app.state.auth.engine) as db:
            charges = list(db.scalars(select(Charge)))
            assert len(charges) == 1 and charges[0].state == "reserved"


def test_sse_revalidates_expiry_without_cancelling_provider(
    settings_factory: Callable[..., Settings],
) -> None:
    from datetime import UTC, datetime, timedelta

    now = [datetime(2031, 1, 1, tzinfo=UTC)]

    class ExpiringProvider(ControlledProvider):
        async def stream(self, payload):
            self.calls.append(payload)
            yield Chunk(text="partial", generation_id="synthetic-id")
            await asyncio.sleep(0.25)
            now[0] += timedelta(seconds=2)
            await asyncio.sleep(30)
            yield Chunk(text="late")

    provider = ExpiringProvider()
    app = create_app(
        settings_factory(session_absolute_seconds=1), clock=lambda: now[0], chat_provider=provider
    )
    with TestClient(app) as client:
        headers = signin(client)
        result = start(client, headers, new_conversation(client, headers)).json()
        response = client.get(f"/api/runs/{result['id']}/events")
        assert "event: session.expired" in response.text
        assert '"output": "partiallate"' not in response.text
        assert len(provider.calls) == 1
        assert client.get(f"/api/runs/{result['id']}").status_code == 401


def test_explicit_metadata_reconciliation_is_idempotent(
    settings_factory: Callable[..., Settings],
) -> None:
    class ReconciledProvider(ControlledProvider):
        async def generation(self, generation_id):
            return {"id": generation_id, "total_cost": "0.000321", "tokens_prompt": 9}

    provider = ReconciledProvider(missing_usage=True)
    with TestClient(create_app(settings_factory(), chat_provider=provider)) as client:
        headers = signin(client)
        result = start(client, headers, new_conversation(client, headers)).json()
        finish(client, result["id"])
        # Metadata may be reconciled immediately after the stream completes.
        reconciled = client.post(f"/api/runs/{result['id']}/reconcile", headers=headers).json()
        assert reconciled["actual_microusd"] == 321
        assert reconciled["accounting_state"] == "settled"
        client.post(f"/api/runs/{result['id']}/reconcile", headers=headers)
        assert client.get("/api/usage").json()["daily_actual_microusd"] == 321


def test_live_test_and_per_request_allowances_reserve_before_dispatch(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = ControlledProvider(delay=30)
    config = settings_factory(
        provider_mode="openrouter",
        openrouter_api_key="synthetic-key",
        max_request_usd="0.01",
        daily_budget_usd="1",
        live_test_budget_usd="0.0001",
    )
    app = create_app(config, chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        first = new_conversation(client, headers)
        assert start(client, headers, first, request_allowance_microusd=1).status_code == 402
        accepted = start(client, headers, first, verification_run=True)
        assert accepted.status_code == 202
        second = new_conversation(client, headers)
        rejected = start(client, headers, second, verification_run=True)
        assert rejected.status_code == 402
        assert rejected.json()["error"]["code"] == "live_test_budget"
        with Session(app.state.auth.engine) as db:
            assert db.scalar(select(Charge)).purpose == "verification"
