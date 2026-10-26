import base64
import io
from collections.abc import Callable

import pytest
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import Attachment
from tests.test_bootstrap import signin
from tests.test_chat import ControlledProvider, finish, new_conversation, start


def png(width: int = 32, height: int = 24) -> bytes:
    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "synthetic metadata")
    Image.new("RGB", (width, height), "green").save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()


def pdf(text: str | None = "PDF fixture text", encrypted: bool = False, pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=300, height=200)
        if text:
            font = writer._add_object(
                DictionaryObject(
                    {
                        NameObject("/Type"): NameObject("/Font"),
                        NameObject("/Subtype"): NameObject("/Type1"),
                        NameObject("/BaseFont"): NameObject("/Helvetica"),
                    }
                )
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
            )
            content = DecodedStreamObject()
            content.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode())
            page[NameObject("/Contents")] = writer._add_object(content)
    if encrypted:
        writer.encrypt("synthetic-fixture-password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def docx() -> bytes:
    document = Document()
    document.add_paragraph("DOCX fixture text")
    document.part.relate_to(
        "http://169.254.169.254/never-fetch", RELATIONSHIP_TYPE.HYPERLINK, is_external=True
    )
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def upload(client: TestClient, headers: dict[str, str], name: str, data: bytes, mime: str):
    return client.post("/api/attachments", headers=headers, files=[("files", (name, data, mime))])


@pytest.mark.parametrize(
    "name,data,mime,expected",
    [
        ("fixture.txt", b"Text fixture", "text/plain", "Text fixture"),
        ("fixture.md", b"# Markdown fixture", "text/markdown", "Markdown fixture"),
        ("fixture.csv", b"name,value\nfixture,3", "text/csv", "fixture,3"),
        ("fixture.pdf", pdf(), "application/pdf", "PDF fixture text"),
        (
            "fixture.docx",
            docx(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "DOCX fixture text",
        ),
    ],
)
def test_real_extraction_and_text_forwarding(
    name, data, mime, expected, settings_factory: Callable[..., Settings]
) -> None:
    provider = ControlledProvider()
    with TestClient(create_app(settings_factory(), chat_provider=provider)) as client:
        headers = signin(client)
        response = upload(client, headers, name, data, mime)
        assert response.status_code == 201, response.text
        item = response.json()[0]
        assert expected in item["preview"] and item["status"] == "ready"
        result = start(
            client, headers, new_conversation(client, headers), attachment_ids=[item["id"]]
        ).json()
        finish(client, result["id"])
        context = provider.calls[0]["messages"][-1]["content"]
        assert expected in context and "untrusted data" in context
        assert "_attachments" not in provider.calls[0]["messages"][-1]


def test_images_are_normalized_forwarded_as_images_and_reused(
    settings_factory: Callable[..., Settings],
) -> None:
    provider = ControlledProvider()
    app = create_app(settings_factory(max_image_edge=16), chat_provider=provider)
    with TestClient(app) as client:
        headers = signin(client)
        response = upload(client, headers, "screen.png", png(), "image/png")
        assert response.status_code == 201, response.text
        item = response.json()[0]
        assert item["mime"] == "image/webp" and max(item["width"], item["height"]) == 16
        binary = client.get(f"/api/attachments/{item['id']}")
        with Image.open(io.BytesIO(binary.content)) as image:
            assert not image.getexif() and "private" not in image.info
        conversation_id = new_conversation(client, headers)
        first = start(client, headers, conversation_id, attachment_ids=[item["id"]]).json()
        finish(client, first["id"])
        content = provider.calls[0]["messages"][-1]["content"]
        assert content[1]["type"] == "image_url"
        assert base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1]) == binary.content
        again = start(
            client, headers, conversation_id, retry_of=first["id"], model_id="mock/clear", prompt=""
        ).json()
        finish(client, again["id"])
        assert provider.calls[1]["messages"] == provider.calls[0]["messages"]
        with Session(app.state.auth.engine) as db:
            assert len(list(db.scalars(select(Attachment)))) == 1
        assert client.delete(f"/api/attachments/{item['id']}", headers=headers).status_code == 409


@pytest.mark.parametrize(
    "name,data,mime",
    [
        ("../secret.txt", b"fixture", "text/plain"),
        ("screen.png", png(), "image/jpeg"),
        ("screen.jpg", png(), "image/jpeg"),
        ("page.html", b"<html>fixture</html>", "text/html"),
        ("image.svg", b"<svg/>", "image/svg+xml"),
        ("archive.zip", b"PK\x03\x04", "application/zip"),
        ("macro.docm", b"PK\x03\x04", "application/vnd.ms-word.document.macroEnabled.12"),
    ],
)
def test_unsafe_formats_mime_and_paths_are_rejected(
    name, data, mime, settings_factory: Callable[..., Settings]
) -> None:
    config = settings_factory()
    with TestClient(create_app(config)) as client:
        response = upload(client, signin(client), name, data, mime)
        assert response.status_code == 422, response.text
        assert not list((config.data_dir / "files").iterdir())
        assert not list((config.data_dir / ".work").iterdir())


def test_encryption_empty_extraction_and_resource_limits(
    settings_factory: Callable[..., Settings],
) -> None:
    with TestClient(create_app(settings_factory(max_pdf_pages=1, max_image_pixels=100))) as client:
        headers = signin(client)
        assert (
            upload(client, headers, "encrypted.pdf", pdf(encrypted=True), "application/pdf").json()[
                "error"
            ]["code"]
            == "encrypted_document"
        )
        assert (
            upload(client, headers, "pages.pdf", pdf(pages=2), "application/pdf").json()["error"][
                "code"
            ]
            == "page_limit"
        )
        assert (
            upload(client, headers, "large.png", png(), "image/png").json()["error"]["code"]
            == "image_limits"
        )
        empty = upload(client, headers, "scan.pdf", pdf(text=None), "application/pdf").json()[0]
        assert empty["status"] == "empty" and "OCR" in empty["warnings"][0]
        rejected = start(
            client, headers, new_conversation(client, headers), attachment_ids=[empty["id"]]
        )
        assert rejected.status_code == 422 and rejected.json()["error"]["code"] == "empty_document"


def test_streamed_size_limit_and_gc(settings_factory: Callable[..., Settings]) -> None:
    config = settings_factory(max_upload_file_bytes=128, max_upload_total_bytes=256)
    app = create_app(config)
    with TestClient(app) as client:
        headers = signin(client)
        assert upload(client, headers, "oversized.txt", b"x" * 129, "text/plain").status_code == 413
        item = upload(client, headers, "orphan.txt", b"fixture", "text/plain").json()[0]
        with Session(app.state.auth.engine) as db:
            record = db.get(Attachment, item["id"])
            record.created_at -= 86401
            db.commit()
        app.state.attachments.collect()
        assert client.get(f"/api/attachments/{item['id']}").status_code == 404


def test_stream_limit_ignores_forged_content_length(
    settings_factory: Callable[..., Settings],
) -> None:
    config = settings_factory(max_upload_total_bytes=256, max_upload_file_bytes=128)
    with TestClient(create_app(config)) as client:
        headers = signin(client)
        body = (
            b'--fixture\r\nContent-Disposition: form-data; name="files"; filename="large.txt"\r\n'
            b"Content-Type: text/plain\r\n\r\n" + b"x" * 300000 + b"\r\n--fixture--\r\n"
        )
        response = client.post(
            "/api/attachments",
            headers={
                **headers,
                "Content-Type": "multipart/form-data; boundary=fixture",
                "Content-Length": "1",
            },
            content=(body[offset : offset + 1024] for offset in range(0, len(body), 1024)),
        )
        assert response.status_code == 413, response.text
        assert not list((config.data_dir / "files").iterdir())


def test_separate_uploads_cannot_bypass_combined_context_limit(
    settings_factory: Callable[..., Settings],
) -> None:
    config = settings_factory(max_upload_total_bytes=100, max_upload_file_bytes=100)
    provider = ControlledProvider()
    with TestClient(create_app(config, chat_provider=provider)) as client:
        headers = signin(client)
        identifiers = [
            upload(client, headers, f"part-{index}.txt", b"x" * 60, "text/plain").json()[0]["id"]
            for index in range(2)
        ]
        result = start(
            client, headers, new_conversation(client, headers), attachment_ids=identifiers
        )
        assert result.status_code == 413
        assert not provider.calls


@pytest.mark.parametrize(
    "unsafe_name,xml",
    [
        ("../outside", b"fixture"),
        ("word/vbaProject.bin", b"fixture"),
        (
            "word/document.xml",
            b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///synthetic-never-read">]><x>&y;</x>',
        ),
    ],
)
def test_docx_unsafe_package_features_are_rejected(
    unsafe_name, xml, settings_factory: Callable[..., Settings]
) -> None:
    from zipfile import ZIP_DEFLATED, ZipFile

    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        if unsafe_name != "word/document.xml":
            archive.writestr("word/document.xml", "<document />")
        archive.writestr(unsafe_name, xml)
    with TestClient(create_app(settings_factory())) as client:
        response = upload(
            client,
            signin(client),
            "unsafe.docx",
            output.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] in {"unsafe_document", "unsafe_archive"}
