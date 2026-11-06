import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import digest
from app.main import create_app
from app.models import Charge, Run
from app.services.runs import RunStart
from tests.test_attachments import png, upload
from tests.test_bootstrap import signin
from tests.test_chat import ControlledProvider, finish, new_conversation, start


def completed(client, headers, conversation, **options):
    response = start(client, headers, conversation, **options)
    assert response.status_code == 202, response.text
    return finish(client, response.json()["id"])


def test_independent_inputs_send_only_current_files_and_restore_text_context(settings_factory):
    provider = ControlledProvider()
    app = create_app(settings_factory(), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        conversation = new_conversation(client, headers)
        old_doc = upload(client, headers, "old.txt", b"OLD_DOCUMENT_DATA", "text/plain").json()[0]
        old_prompt = ("Earlier question " + "background " * 500).strip()
        first = completed(
            client, headers, conversation, prompt=old_prompt, attachment_ids=[old_doc["id"]]
        )
        capture = upload(client, headers, "current.png", png(), "image/png").json()[0]
        current_doc = upload(
            client, headers, "current.txt", b"CURRENT_DOCUMENT_DATA", "text/plain"
        ).json()[0]
        independent = completed(
            client,
            headers,
            conversation,
            prompt="Analyze this capture",
            system_prompt="Be concise",
            without_context=True,
            attachment_ids=[capture["id"], current_doc["id"]],
        )
        payload = provider.calls[-1]["messages"]
        assert [message["role"] for message in payload] == ["system", "user"]
        assert payload[0]["content"] == "Be concise"
        assert "CURRENT_DOCUMENT_DATA" in json.dumps(payload)
        assert "OLD_DOCUMENT_DATA" not in json.dumps(payload)
        assert old_prompt not in json.dumps(payload)
        assert sum(part["type"] == "image_url" for part in payload[-1]["content"]) == 1
        assert {item["id"] for item in independent["attachments"]} == {
            capture["id"],
            current_doc["id"],
        }
        assert independent["settings"]["without_context"] is True
        assert independent["settings"]["context_parent_run_id"] == first["id"]
        last = completed(
            client, headers, conversation, prompt="Unrelated question", without_context=True
        )
        assert provider.calls[-1]["messages"] == [{"role": "user", "content": "Unrelated question"}]
        assert last["reserved_microusd"] < first["reserved_microusd"]
        with Session(app.state.auth.engine) as db:
            originals = {
                run.id: (run.snapshot_json, run.settings_json) for run in db.scalars(select(Run))
            }
        completed(
            client, headers, conversation, prompt="Use the conversation", system_prompt="New system"
        )
        assert provider.calls[-1]["messages"] == [
            {"role": "system", "content": "New system"},
            {"role": "user", "content": old_prompt},
            {"role": "assistant", "content": "Partial answer"},
            {"role": "user", "content": "Analyze this capture"},
            {"role": "assistant", "content": "Partial answer"},
            {"role": "user", "content": "Unrelated question"},
            {"role": "assistant", "content": "Partial answer"},
            {"role": "user", "content": "Use the conversation"},
        ]
        assert len(client.get(f"/api/conversations/{conversation}").json()["runs"]) == 4
        with Session(app.state.auth.engine) as db:
            for run_id, original in originals.items():
                saved = db.get(Run, run_id)
                assert (saved.snapshot_json, saved.settings_json) == original


def test_independent_replay_edit_and_fork_preserve_selected_branch(settings_factory):
    provider = ControlledProvider()
    with TestClient(create_app(settings_factory(), chat_provider=provider)) as client:
        headers = signin(client)
        conversation = new_conversation(client, headers)
        first = completed(client, headers, conversation, prompt="Original history")
        source = completed(
            client, headers, conversation, prompt="Independent source", without_context=True
        )
        completed(client, headers, conversation, prompt="Later branch")
        repeated = completed(client, headers, conversation, retry_of=source["id"], prompt="")
        assert provider.calls[-1]["messages"] == [{"role": "user", "content": source["prompt"]}]
        assert repeated["settings"]["without_context"] is True
        assert repeated["settings"]["context_parent_run_id"] == first["id"]
        edited = completed(
            client, headers, conversation, retry_of=source["id"], prompt="Edited source"
        )
        assert provider.calls[-1]["messages"] == [{"role": "user", "content": "Edited source"}]
        completed(client, headers, conversation, prompt="After editing")
        assert [message["content"] for message in provider.calls[-1]["messages"]] == [
            "Original history",
            "Partial answer",
            "Edited source",
            "Partial answer",
            "After editing",
        ]
        fork = client.post(f"/api/runs/{edited['id']}/fork", headers=headers)
        assert fork.status_code == 201, fork.text
        saved = fork.json()
        assert saved["runs"][0]["settings"]["context_parent_run_id"] is None
        completed(client, headers, saved["id"], prompt="Continue chosen input")
        assert provider.calls[-1]["messages"] == [
            {"role": "user", "content": "Edited source"},
            {"role": "assistant", "content": "Partial answer"},
            {"role": "user", "content": "Continue chosen input"},
        ]
        completed(
            client, headers, conversation, retry_of=first["id"], prompt="", without_context=True
        )
        assert provider.calls[-1]["messages"] == [{"role": "user", "content": "Original history"}]
        assert (
            client.get(f"/api/conversations/{conversation}").json()["runs"][-1]["settings"][
                "without_context"
            ]
            is False
        )


def test_independent_history_survives_restart_and_excludes_failed_turns(settings_factory):
    config = settings_factory()
    provider = ControlledProvider()
    with TestClient(create_app(config, chat_provider=provider)) as client:
        headers = signin(client)
        conversation = new_conversation(client, headers)
        completed(client, headers, conversation, prompt="Saved first", without_context=True)
        provider.fail = True
        failed = completed(
            client, headers, conversation, prompt="Failed input", without_context=True
        )
        assert failed["status"] == "failed"
        token = client.cookies[config.cookie_name]
    replacement = ControlledProvider()
    with TestClient(create_app(config, chat_provider=replacement)) as client:
        client.cookies.set(config.cookie_name, token)
        completed(client, headers, conversation, prompt="Restored context")
        assert replacement.calls[-1]["messages"] == [
            {"role": "user", "content": "Saved first"},
            {"role": "assistant", "content": "Partial answer"},
            {"role": "user", "content": "Restored context"},
        ]


@pytest.mark.parametrize("invalid_parent", ["missing", "cycle", "foreign"])
def test_invalid_independent_parent_is_rejected_without_dispatch(settings_factory, invalid_parent):
    provider = ControlledProvider()
    app = create_app(settings_factory(), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        conversation = new_conversation(client, headers)
        saved = completed(client, headers, conversation, without_context=True)
        foreign = completed(client, headers, new_conversation(client, headers))
        with Session(app.state.auth.engine) as db:
            run = db.get(Run, saved["id"])
            settings = json.loads(run.settings_json)
            settings["context_parent_run_id"] = {
                "missing": "missing",
                "cycle": run.id,
                "foreign": foreign["id"],
            }[invalid_parent]
            run.settings_json = json.dumps(settings)
            db.commit()
        assert start(client, headers, conversation).status_code == 409
        assert len(provider.calls) == 2
        completed(client, headers, conversation, without_context=True)
        assert provider.calls[-1]["messages"] == [{"role": "user", "content": "Hello"}]


def test_context_mode_validation_and_legacy_idempotency(settings_factory):
    provider = ControlledProvider()
    app = create_app(settings_factory(), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        conversation = new_conversation(client, headers)
        key = uuid4().hex
        body = RunStart(
            conversation_id=conversation,
            model_id="mock/steady",
            prompt="Hello",
            idempotency_key=key,
            max_tokens=128,
        )
        legacy_hash = digest(
            json.dumps(body.model_dump(exclude={"without_context"}), sort_keys=True)
        )
        saved = completed(client, headers, conversation, idempotency_key=key)
        with Session(app.state.auth.engine) as db:
            charge = db.scalar(select(Charge).where(Charge.run_id == saved["id"]))
            assert charge.request_hash == legacy_hash
        same = start(client, headers, conversation, idempotency_key=key, without_context=False)
        assert same.status_code == 202 and same.json()["id"] == saved["id"]
        assert (
            start(
                client, headers, conversation, idempotency_key=key, without_context=True
            ).status_code
            == 409
        )
        for invalid in ["false", "true", 1, None]:
            assert start(client, headers, conversation, without_context=invalid).status_code == 422
        assert len(provider.calls) == 1
