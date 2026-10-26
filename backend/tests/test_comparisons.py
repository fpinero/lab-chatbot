import asyncio
import json
import time
from collections.abc import Callable
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import Charge, Comparison, Run
from app.providers.chat import Chunk, ProviderError
from tests.test_attachments import png, upload
from tests.test_bootstrap import signin
from tests.test_chat import ControlledProvider, finish, new_conversation, start


class Candidates(ControlledProvider):
    def __init__(self, fail_clear: bool = False, incompatible: bool = False):
        super().__init__()
        self.fail_clear, self.incompatible = fail_clear, incompatible
        self.active = 0
        self.maximum_active = 0

    async def catalog(self):
        result = await super().catalog()
        if self.incompatible:
            result[1]["architecture"]["input_modalities"] = ["text"]
        return result

    async def stream(self, payload):
        self.calls.append(payload)
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        try:
            yield Chunk(
                text=f"Answer from {payload['model']}",
                generation_id=f"synthetic-{payload['model']}",
                provider="Synthetic provider",
            )
            await asyncio.sleep(0.15)
            if self.fail_clear and payload["model"] == "mock/clear":
                raise ProviderError("provider_stream_failed")
            yield Chunk(usage={"cost": "0.000123", "prompt_tokens": 8, "completion_tokens": 4})
        finally:
            self.active -= 1


def compare(client, headers, conversation_id, **overrides):
    body = {
        "conversation_id": conversation_id,
        "model_ids": ["mock/steady", "mock/clear"],
        "idempotency_key": uuid4().hex,
        "prompt": "Common snapshot",
        "max_tokens": 128,
    }
    body.update(overrides)
    return client.post("/api/comparisons", headers=headers, json=body)


def completed_group(client, group_id):
    for _ in range(100):
        value = client.get(f"/api/comparisons/{group_id}").json()
        if value["status"] != "running":
            return value
        time.sleep(0.02)
    raise AssertionError("Comparison did not finish")


def test_four_candidates_share_exact_snapshot_and_two_global_slots(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = Candidates()
    app = create_app(settings_factory(), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        conversation_id = new_conversation(client, headers)
        key = uuid4().hex
        selected = ["mock/steady", "mock/clear", "mock/brief", "mock/deep"]
        response = compare(
            client, headers, conversation_id, model_ids=selected, idempotency_key=key
        )
        assert response.status_code == 202, response.text
        group_id = response.json()["id"]
        duplicate = compare(
            client, headers, conversation_id, model_ids=selected, idempotency_key=key
        )
        assert duplicate.json()["id"] == group_id
        final = completed_group(client, group_id)
        assert final["status"] == "succeeded" and len(final["candidates"]) == 4
        assert provider.maximum_active == 2 and len(provider.calls) == 4
        assert all(call["messages"] == provider.calls[0]["messages"] for call in provider.calls)
        assert all("Answer from" not in json.dumps(call["messages"]) for call in provider.calls)
        assert max(run["queue_delay_ms"] for run in final["candidates"]) >= 100
        with Session(app.state.auth.engine) as db:
            group = db.get(Comparison, group_id)
            assert all(run.snapshot_json == group.snapshot_json for run in db.scalars(select(Run)))
            assert len(list(db.scalars(select(Charge)))) == 4


def test_partial_failure_explicit_retry_preserves_original_evidence(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = Candidates(fail_clear=True)
    with TestClient(create_app(settings_factory(), chat_provider=provider)) as client:
        headers = signin(client)
        conversation_id = new_conversation(client, headers)
        group = completed_group(client, compare(client, headers, conversation_id).json()["id"])
        assert group["status"] == "partial_failure"
        failed = next(run for run in group["candidates"] if run["status"] == "failed")
        provider.fail_clear = False
        retried = start(
            client,
            headers,
            conversation_id,
            model_id=failed["model_id"],
            retry_of=failed["id"],
            prompt="",
        ).json()
        finish(client, retried["id"])
        updated = client.get(f"/api/comparisons/{group['id']}").json()
        assert updated["status"] == "succeeded" and updated["previous_runs_count"] == 1
        assert client.get(f"/api/runs/{failed['id']}").json()["status"] == "failed"
        assert provider.calls[2]["messages"] == provider.calls[0]["messages"]


def test_every_candidate_is_validated_before_any_spend(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = Candidates(incompatible=True)
    app = create_app(settings_factory(), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        conversation_id = new_conversation(client, headers)
        image = upload(client, headers, "screen.png", png(), "image/png").json()[0]
        response = compare(client, headers, conversation_id, attachment_ids=[image["id"]])
        assert (
            response.status_code == 422
            and response.json()["error"]["code"] == "incompatible_attachment"
        )
        assert not provider.calls
        with Session(app.state.auth.engine) as db:
            assert not list(db.scalars(select(Charge)))
        assert (
            compare(
                client, headers, conversation_id, model_ids=["mock/steady", "unknown"]
            ).status_code
            == 422
        )


def test_combined_budget_is_reserved_atomically(settings_factory: Callable[..., Settings]) -> None:
    provider = Candidates()
    config = settings_factory(
        provider_mode="openrouter",
        openrouter_api_key="synthetic-key",
        max_request_usd="0.0001",
        daily_budget_usd="1",
    )
    app = create_app(config, chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        response = compare(client, headers, new_conversation(client, headers))
        assert response.status_code == 402, response.text
        assert provider.calls == []
        with Session(app.state.auth.engine) as db:
            assert not list(db.scalars(select(Charge)))
            assert not list(db.scalars(select(Comparison)))


def test_continue_forks_context_without_billing_and_gc_keeps_shared_files(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = Candidates()
    app = create_app(settings_factory(), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        image = upload(client, headers, "screen.png", png(), "image/png").json()[0]
        conversation_id = new_conversation(client, headers)
        group = completed_group(
            client,
            compare(client, headers, conversation_id, attachment_ids=[image["id"]]).json()["id"],
        )
        chosen = group["candidates"][0]
        before = client.get("/api/usage").json()["daily_actual_microusd"]
        fork = client.post(f"/api/runs/{chosen['id']}/fork", headers=headers)
        assert fork.status_code == 201, fork.text
        forked = fork.json()
        assert forked["runs"][0]["accounting_state"] == "inherited"
        assert client.get("/api/usage").json()["daily_actual_microusd"] == before
        assert (
            client.delete(
                f"/api/conversations/{conversation_id}?confirm=true", headers=headers
            ).status_code
            == 204
        )
        assert client.get(f"/api/attachments/{image['id']}").status_code == 200
        with Session(app.state.auth.engine) as db:
            records = list(db.scalars(select(Charge)))
            assert all(record.run_id is None for record in records)
            assert all(json.loads(record.price_json)["generation_id"] for record in records)
        assert (
            client.delete(
                f"/api/conversations/{forked['id']}?confirm=true", headers=headers
            ).status_code
            == 204
        )
        assert client.get(f"/api/attachments/{image['id']}").status_code == 404


def test_continuation_uses_only_the_chosen_answer(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = Candidates()
    with TestClient(create_app(settings_factory(), chat_provider=provider)) as client:
        headers = signin(client)
        original = new_conversation(client, headers)
        group = completed_group(client, compare(client, headers, original).json()["id"])
        chosen = next(item for item in group["candidates"] if item["model_id"] == "mock/clear")
        fork = client.post(f"/api/runs/{chosen['id']}/fork", headers=headers).json()
        next_run = start(client, headers, fork["id"], prompt="Continue deliberately").json()
        finish(client, next_run["id"])
        messages = provider.calls[-1]["messages"]
        assistants = [message["content"] for message in messages if message["role"] == "assistant"]
        assert assistants == [chosen["output"]]
        assert "mock/steady" not in json.dumps(messages)
