import base64
import io
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import Attachment, Charge, Conversation, Run, RunAttachment
from app.providers.chat import ProviderKeyBudget
from app.services.catalog import ModelInfo
from tests.test_bootstrap import signin
from tests.test_chat import ControlledProvider, finish, new_conversation, start


def temporary(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/temporary-chats", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def send(client: TestClient, headers: dict[str, str], identifier: str, **values: Any):
    body = {
        "conversation_id": identifier,
        "model_id": "mock/steady",
        "prompt": "Private sentinel prompt",
        "idempotency_key": uuid4().hex,
        "max_tokens": 128,
        **values,
    }
    return client.post(f"/api/temporary-chats/{identifier}/runs", headers=headers, json=body)


def done(client: TestClient, identifier: str, run: str) -> dict[str, Any]:
    for _ in range(100):
        result = client.get(f"/api/temporary-chats/{identifier}/runs/{run}").json()
        if result["status"] in {"succeeded", "failed", "interrupted", "cancelled"}:
            return result
        time.sleep(0.02)
    raise AssertionError("Temporary run did not finish")


def test_private_content_never_reaches_durable_tables_or_files(
    settings_factory: Callable[..., Settings],
) -> None:
    config = settings_factory()
    provider = ControlledProvider()
    app = create_app(config, chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        identifier = temporary(client, headers)
        with app.state.temporary.chats[identifier].engine.connect() as memory:
            assert memory.exec_driver_sql("PRAGMA database_list").fetchone()[2] == ""
        key = uuid4().hex
        response = send(
            client,
            headers,
            identifier,
            system_prompt="Private system sentinel",
            idempotency_key=key,
        )
        assert response.status_code == 201, response.text
        run = done(client, identifier, response.json()["id"])
        assert run["status"] == "succeeded" and run["actual_microusd"] == 123
        assert (
            send(
                client,
                headers,
                identifier,
                system_prompt="Private system sentinel",
                idempotency_key=key,
            ).json()["id"]
            == run["id"]
        )
        assert send(client, headers, identifier, idempotency_key=key).status_code == 409
        assert len(provider.calls) == 1
        assert client.get("/api/conversations").json() == []
        assert client.get(f"/api/conversations/{identifier}").status_code == 404
        assert client.get(f"/api/runs/{run['id']}").status_code == 404
        with Session(app.state.runs.engine) as db:
            for model in [Conversation, Run, Attachment, RunAttachment]:
                assert db.scalar(select(func.count()).select_from(model)) == 0
            charge = db.scalar(select(Charge))
            assert charge and charge.purpose == "temporary" and charge.run_id is None
            assert charge.actual_microusd == 123
            assert "Private" not in charge.price_json
        for path in config.data_dir.rglob("*"):
            if path.is_file():
                assert b"Private sentinel" not in path.read_bytes()
                assert b"Private system" not in path.read_bytes()
        assert (
            client.delete(f"/api/temporary-chats/{identifier}", headers=headers).status_code == 204
        )
        assert client.get(f"/api/temporary-chats/{identifier}/runs/{run['id']}").status_code == 410
        other = temporary(client, headers)
        assert send(client, headers, other, idempotency_key=key).status_code == 410
        assert len(provider.calls) == 1
        # Closing a volatile worker must not close the shared provider.
        regular = new_conversation(client, headers)
        normal = start(client, headers, regular)
        assert finish(client, normal.json()["id"])["status"] == "succeeded"


def test_context_opt_out_repeat_edit_and_stream(settings_factory: Callable[..., Settings]) -> None:
    provider = ControlledProvider()
    with TestClient(create_app(settings_factory(), chat_provider=provider)) as client:
        headers = signin(client)
        identifier = temporary(client, headers)
        first = send(
            client, headers, identifier, prompt="First private message", system_prompt="Be concise"
        )
        run = done(client, identifier, first.json()["id"])
        second = send(
            client, headers, identifier, prompt="Second private message", system_prompt="Be concise"
        )
        done(client, identifier, second.json()["id"])
        assert any(m["role"] == "assistant" for m in provider.calls[-1]["messages"])
        isolated = send(
            client, headers, identifier, prompt="Independent private message", without_context=True
        )
        done(client, identifier, isolated.json()["id"])
        assert [m["role"] for m in provider.calls[-1]["messages"]] == ["user"]
        edited = send(
            client,
            headers,
            identifier,
            prompt="Edited private message",
            retry_of=run["id"],
            replace_prompt=True,
        )
        done(client, identifier, edited.json()["id"])
        assert provider.calls[-1]["messages"][-1]["content"] == "Edited private message"
        events = client.get(f"/api/temporary-chats/{identifier}/runs/{edited.json()['id']}/events")
        assert events.status_code == 200 and "event: run.snapshot" in events.text
        assert "no-store" in events.headers["cache-control"]


@pytest.mark.parametrize("document", [False, True])
def test_memory_upload_preview_removal_and_current_turn_only(
    settings_factory: Callable[..., Settings], document: bool
) -> None:
    config = settings_factory()
    provider = ControlledProvider()
    with TestClient(create_app(config, chat_provider=provider)) as client:
        headers = signin(client)
        identifier = temporary(client, headers)
        data = io.BytesIO()
        Image.new("RGB", (40, 25), "green").save(data, format="PNG")
        raw = b"Private document sentinel" if document else data.getvalue()
        item = {
            "name": "private.txt" if document else "private.png",
            "mime": "text/plain" if document else "image/png",
            "data": base64.b64encode(raw).decode(),
        }
        response = client.post(
            f"/api/temporary-chats/{identifier}/attachments",
            headers=headers,
            json={"files": [item]},
        )
        assert response.status_code == 201, response.text
        attachment = response.json()[0]
        media = client.get(f"/api/attachments/{attachment['id']}")
        assert media.status_code == 200 and "no-store" in media.headers["cache-control"]
        if not document:
            assert media.content.startswith(b"RIFF")
        assert (
            send(
                client, headers, identifier, prompt="", attachment_ids=[attachment["id"]]
            ).status_code
            == 422
        )
        first = send(
            client,
            headers,
            identifier,
            prompt="",
            system_prompt="Analyze the attached file",
            attachment_ids=[attachment["id"]],
        )
        assert first.status_code == 201, first.text
        run = done(client, identifier, first.json()["id"])
        assert run["attachments"][0]["id"] == attachment["id"]
        assert (
            client.delete(f"/api/attachments/{attachment['id']}", headers=headers).status_code
            == 409
        )
        second = send(client, headers, identifier, prompt="Text only now")
        done(client, identifier, second.json()["id"])
        assert all(isinstance(m["content"], str) for m in provider.calls[-1]["messages"])
        assert "Private document sentinel" not in json.dumps(provider.calls[-1]["messages"])
        assert not list((config.data_dir / "files").iterdir())
        assert not list((config.data_dir / ".work").iterdir())
        assert (
            client.delete(f"/api/temporary-chats/{identifier}", headers=headers).status_code == 204
        )
        assert client.get(f"/api/attachments/{attachment['id']}").status_code == 410


def test_session_binding_expiry_logout_and_restart(
    settings_factory: Callable[..., Settings],
) -> None:
    now = datetime(2031, 7, 1, tzinfo=UTC)
    config = settings_factory()
    app = create_app(config, clock=lambda: now)
    with TestClient(app) as client:
        headers = signin(client)
        identifier = temporary(client, headers)
        assert client.post(f"/api/temporary-chats/{identifier}/touch").status_code == 403
        now += timedelta(seconds=1800)
        assert (
            client.post(f"/api/temporary-chats/{identifier}/touch", headers=headers).status_code
            == 410
        )
        client.portal.call(app.state.temporary.sweep)
        assert not app.state.temporary.chats
        identifier = temporary(client, headers)
        assert client.post("/api/auth/logout", headers=headers).status_code == 204
        assert not app.state.temporary.chats
        headers = signin(client)
        assert (
            client.post(f"/api/temporary-chats/{identifier}/touch", headers=headers).status_code
            == 410
        )
        identifier = temporary(client, headers)
    with TestClient(create_app(config)) as client:
        headers = signin(client)
        assert (
            client.post(f"/api/temporary-chats/{identifier}/touch", headers=headers).status_code
            == 410
        )


def test_exit_cancels_queued_and_active_runs_and_preserves_accounting(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = ControlledProvider(delay=3)
    app = create_app(settings_factory(), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        identifiers = [temporary(client, headers) for _ in range(3)]
        for identifier in identifiers:
            assert send(client, headers, identifier).status_code == 201
        time.sleep(0.05)
        for identifier in reversed(identifiers):
            assert (
                client.delete(f"/api/temporary-chats/{identifier}", headers=headers).status_code
                == 204
            )
        assert not app.state.temporary.chats
        with Session(app.state.runs.engine) as db:
            charges = list(db.scalars(select(Charge)))
            assert len(charges) == 3
            assert all(c.state in {"settled", "uncertain"} for c in charges)
            assert any(c.actual_microusd == 0 for c in charges)


def test_session_isolation_capacity_and_anonymous_access(
    settings_factory: Callable[..., Settings],
) -> None:
    config = settings_factory()
    app = create_app(config)
    with TestClient(app) as client:
        assert client.post("/api/temporary-chats").status_code == 401
        first_headers = signin(client)
        first_cookie = client.cookies[config.cookie_name]
        identifier = temporary(client, first_headers)
        client.cookies.clear()
        second_headers = signin(client)
        assert (
            client.post(
                f"/api/temporary-chats/{identifier}/touch", headers=second_headers
            ).status_code
            == 410
        )
        for _ in range(3):
            temporary(client, second_headers)
        assert client.post("/api/temporary-chats", headers=second_headers).status_code == 429
        assert client.post("/api/auth/logout", headers=second_headers).status_code == 204
        assert len(app.state.temporary.chats) == 1
        client.cookies.set(config.cookie_name, first_cookie)
        assert (
            client.post(
                f"/api/temporary-chats/{identifier}/touch", headers=first_headers
            ).status_code
            == 204
        )


def test_normal_and_temporary_share_execution_and_queue_limits(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = ControlledProvider(delay=3)
    app = create_app(settings_factory(max_queued_runs=3), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        regular = new_conversation(client, headers)
        assert start(client, headers, regular).status_code == 202
        first, second = temporary(client, headers), temporary(client, headers)
        assert send(client, headers, first).status_code == 201
        assert send(client, headers, second).status_code == 201
        time.sleep(0.05)
        assert len(provider.calls) == 2
        third = temporary(client, headers)
        assert send(client, headers, third).status_code == 429
        other = new_conversation(client, headers)
        assert start(client, headers, other).status_code == 429
        for identifier in [second, first, third]:
            assert (
                client.delete(f"/api/temporary-chats/{identifier}", headers=headers).status_code
                == 204
            )


def test_private_upload_rejects_unsafe_names_magic_and_empty_context(
    settings_factory: Callable[..., Settings],
) -> None:
    config = settings_factory()
    with TestClient(create_app(config)) as client:
        headers = signin(client)
        identifier = temporary(client, headers)
        for name, mime, data in [
            ("../private.txt", "text/plain", b"test"),
            ("private.png", "image/png", b"not png"),
        ]:
            response = client.post(
                f"/api/temporary-chats/{identifier}/attachments",
                headers=headers,
                json={
                    "files": [{"name": name, "mime": mime, "data": base64.b64encode(data).decode()}]
                },
            )
            assert response.status_code == 422
        assert (
            send(client, headers, identifier, prompt="", system_prompt="Only system").status_code
            == 422
        )
        assert not list((config.data_dir / "files").iterdir())


def test_failed_admission_before_dispatch_settles_zero(
    settings_factory: Callable[..., Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = ControlledProvider()
    app = create_app(settings_factory(), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        identifier = temporary(client, headers)
        worker = app.state.temporary.chats[identifier]
        original = worker.runs.create_queued

        def fail(*args: Any, **kwargs: Any) -> Any:
            original(*args, **kwargs)
            raise RuntimeError("Synthetic admission failure")

        monkeypatch.setattr(worker.runs, "create_queued", fail)
        response = send(client, headers, identifier)
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "Synthetic admission failure" not in response.text
        assert not provider.calls
        with Session(app.state.runs.engine) as db:
            charge = db.scalar(select(Charge))
            assert charge and charge.state == "settled" and charge.actual_microusd == 0


def test_private_estimate_uses_latest_shared_provider_balance(
    settings_factory: Callable[..., Settings],
) -> None:
    app = create_app(settings_factory(spend_control="provider"))
    with TestClient(app) as client:
        headers = signin(client)
        identifier = temporary(client, headers)
        worker = app.state.temporary.chats[identifier]
        model = ModelInfo.model_validate(client.get("/api/models").json()["models"][0]).model_copy(
            update={"simulated": False}
        )
        worker.runs.provider_budget = ProviderKeyBudget(
            limit_usd="9.9", remaining_usd="9", used_usd="0.9", checked_at=1
        )
        latest = ProviderKeyBudget(limit_usd="9.9", remaining_usd="4", used_usd="5.9", checked_at=2)
        app.state.runs.provider_budget = latest
        messages = [
            {
                "role": "user",
                "content": "Synthetic image input",
                "_attachments": [{"kind": "image", "width": 16, "height": 16}],
            }
        ]
        assert worker.runs.estimate(model, messages, 128) == 4_000_000
        assert app.state.runs.provider_budget is latest


def test_presence_heartbeat_does_not_extend_authentication(
    settings_factory: Callable[..., Settings],
) -> None:
    now = datetime(2031, 7, 1, tzinfo=UTC)
    app = create_app(settings_factory(session_idle_seconds=120), clock=lambda: now)
    with TestClient(app) as client:
        headers = signin(client)
        identifier = temporary(client, headers)
        now += timedelta(seconds=60)
        assert (
            client.post(f"/api/temporary-chats/{identifier}/touch", headers=headers).status_code
            == 204
        )
        now += timedelta(seconds=60)
        assert (
            client.post(f"/api/temporary-chats/{identifier}/touch", headers=headers).status_code
            == 401
        )
        client.portal.call(app.state.temporary.sweep)
        assert not app.state.temporary.chats
