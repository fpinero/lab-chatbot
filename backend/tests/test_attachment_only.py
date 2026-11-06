import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
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


def test_document_only_and_image_without_system_are_valid_but_empty_input_is_not(settings_factory):
    provider = ControlledProvider()
    with TestClient(create_app(settings_factory(), chat_provider=provider)) as client:
        headers = signin(client)
        conversation = new_conversation(client, headers)
        assert (
            start(client, headers, conversation, prompt="  ", system_prompt="Analyze").status_code
            == 422
        )
        assert (
            start(client, headers, conversation, prompt="", attachment_ids=["missing"]).status_code
            == 404
        )
        assert not provider.calls
        document = upload(client, headers, "note.txt", b"CURRENT_DOCUMENT", "text/plain").json()[0]
        completed(client, headers, conversation, prompt="", attachment_ids=[document["id"]])
        assert "CURRENT_DOCUMENT" in provider.calls[-1]["messages"][-1]["content"]
        image = upload(client, headers, "capture.png", png(), "image/png").json()[0]
        completed(
            client,
            headers,
            conversation,
            prompt="",
            attachment_ids=[image["id"]],
            without_context=True,
        )
        assert len(provider.calls[-1]["messages"]) == 1
        assert [part["type"] for part in provider.calls[-1]["messages"][0]["content"]] == [
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
