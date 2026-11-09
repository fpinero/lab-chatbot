import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Charge, Run
from tests.test_attachments import png, upload
from tests.test_bootstrap import signin
from tests.test_chat import ControlledProvider, new_conversation, start
from tests.test_context_mode import completed


@pytest.mark.parametrize("independent", [False, True])
def test_image_only_input_keeps_system_and_saved_files_on_repeat_and_edit(
    settings_factory, independent
):
    provider = ControlledProvider()
    with TestClient(create_app(settings_factory(), chat_provider=provider)) as client:
        headers = signin(client)
        conversation = new_conversation(client, headers)
        completed(client, headers, conversation, prompt="Earlier unrelated question")
        image = upload(client, headers, "capture.png", png(), "image/png").json()[0]
        saved = completed(
            client,
            headers,
            conversation,
            prompt="",
            system_prompt="Analyze the current image",
            attachment_ids=[image["id"]],
            without_context=independent,
        )
        payload = provider.calls[-1]["messages"]
        assert payload[0] == {"role": "system", "content": "Analyze the current image"}
        assert [part["type"] for part in payload[-1]["content"]] == ["image_url"]
        assert saved["prompt"] == ""
        assert [item["id"] for item in saved["attachments"]] == [image["id"]]
        if independent:
            assert len(payload) == 2
            assert "Earlier unrelated" not in json.dumps(payload)
        repeated = completed(client, headers, conversation, prompt="", retry_of=saved["id"])
        assert provider.calls[-1]["messages"] == payload
        assert repeated["prompt"] == ""
        text_image = completed(
            client,
            headers,
            conversation,
            prompt="Text to remove",
            system_prompt="Analyze the current image",
            attachment_ids=[image["id"]],
            without_context=True,
        )
        edited = completed(
            client,
            headers,
            conversation,
            prompt="  ",
            retry_of=text_image["id"],
            replace_prompt=True,
        )
        assert edited["prompt"] == ""
        assert provider.calls[-1]["messages"] == [payload[0], payload[-1]]
        completed(client, headers, conversation, prompt="Follow up")
        assert provider.calls[-1]["messages"][-3:] == [
            {"role": "user", "content": "[Earlier input with attachments omitted.]"},
            {"role": "assistant", "content": "Partial answer"},
            {"role": "user", "content": "Follow up"},
        ]
        assert all(
            isinstance(message["content"], str) for message in provider.calls[-1]["messages"]
        )
        history = client.get(f"/api/conversations/{conversation}").json()["runs"]
        assert history[1]["prompt"] == "" and history[1]["attachments"][0]["id"] == image["id"]
        assert history[3]["prompt"] == "Text to remove"


def test_attachment_only_requires_system_instructions_and_empty_input_is_rejected(settings_factory):
    provider = ControlledProvider()
    with TestClient(create_app(settings_factory(), chat_provider=provider)) as client:
        headers = signin(client)
        conversation = new_conversation(client, headers)
        assert (
            start(client, headers, conversation, prompt="  ", system_prompt="Analyze").status_code
            == 422
        )
        assert (
            start(
                client,
                headers,
                conversation,
                prompt="",
                system_prompt="Analyze",
                attachment_ids=["missing"],
            ).status_code
            == 404
        )
        assert not provider.calls
        document = upload(client, headers, "note.txt", b"CURRENT_DOCUMENT", "text/plain").json()[0]
        completed(
            client,
            headers,
            conversation,
            prompt="",
            system_prompt="Analyze",
            attachment_ids=[document["id"]],
        )
        assert "CURRENT_DOCUMENT" in provider.calls[-1]["messages"][-1]["content"]
        image = upload(client, headers, "capture.png", png(), "image/png").json()[0]
        for item in [image, document]:
            for system in ["", " \n\t"]:
                rejected = start(
                    client,
                    headers,
                    conversation,
                    prompt="  ",
                    attachment_ids=[item["id"]],
                    system_prompt=system,
                )
                assert rejected.status_code == 422
        assert len(provider.calls) == 1
        completed(
            client,
            headers,
            conversation,
            prompt="",
            attachment_ids=[image["id"]],
            system_prompt="Analyze the image",
            without_context=True,
        )
        assert provider.calls[-1]["messages"][0] == {
            "role": "system",
            "content": "Analyze the image",
        }
        assert [part["type"] for part in provider.calls[-1]["messages"][-1]["content"]] == [
            "image_url"
        ]
        text = completed(client, headers, conversation, prompt="Text only")
        assert (
            start(
                client, headers, conversation, prompt="", retry_of=text["id"], replace_prompt=True
            ).status_code
            == 422
        )
        assert (
            start(client, headers, conversation, prompt="New", replace_prompt=True).status_code
            == 422
        )
        assert len(provider.calls) == 3


def test_saved_inputs_need_their_own_instructions_without_reserving_rejected_requests(
    settings_factory,
):
    provider = ControlledProvider()
    app = create_app(settings_factory(), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        conversation = new_conversation(client, headers)
        image = upload(client, headers, "capture.png", png(), "image/png").json()[0]
        source = completed(
            client, headers, conversation, prompt="Analyze this", attachment_ids=[image["id"]]
        )
        legacy = completed(
            client,
            headers,
            conversation,
            prompt="",
            system_prompt="Analyze",
            attachment_ids=[image["id"]],
        )
        with Session(app.state.auth.engine) as db:
            run = db.get(Run, legacy["id"])
            run.snapshot_json = json.dumps(
                [
                    message
                    for message in json.loads(run.snapshot_json)
                    if message["role"] != "system"
                ]
            )
            settings = json.loads(run.settings_json)
            settings["system_prompt"] = ""
            run.settings_json = json.dumps(settings)
            db.commit()
            original = (run.snapshot_json, run.settings_json)
            charges = db.scalar(select(func.count()).select_from(Charge))
        for identifier, replace in [(legacy["id"], False), (source["id"], True)]:
            rejected = start(
                client,
                headers,
                conversation,
                prompt="",
                retry_of=identifier,
                replace_prompt=replace,
                system_prompt="Cannot override saved instructions",
            )
            assert rejected.status_code == 422
            assert rejected.json()["error"]["code"] == "missing_instructions"
        assert len(provider.calls) == 2
        with Session(app.state.auth.engine) as db:
            assert db.scalar(select(func.count()).select_from(Charge)) == charges
            run = db.get(Run, legacy["id"])
            assert (run.snapshot_json, run.settings_json) == original
        completed(
            client,
            headers,
            conversation,
            prompt="Analyze this image",
            retry_of=legacy["id"],
            replace_prompt=True,
        )
        assert provider.calls[-1]["messages"][-1]["content"][0] == {
            "type": "text",
            "text": "Analyze this image",
        }
