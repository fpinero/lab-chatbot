from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.version import image_version
from tests.conftest import TEST_PASSWORD
from tests.test_bootstrap import ORIGIN


@pytest.mark.parametrize("tag", ["9", "1.2.3", "v2.0.0-rc.1"])
def test_image_metadata_preserves_the_exact_tag(tmp_path: Path, tag: str) -> None:
    marker = tmp_path / "version"
    marker.write_text(tag + "\n")
    assert image_version(marker) == tag


def test_source_checkout_has_no_invented_release(tmp_path: Path) -> None:
    assert image_version(tmp_path / "absent") is None


@pytest.mark.parametrize("tag", ["", "<script>", "a" * 129, "9\nother", "../9"])
def test_invalid_image_metadata_is_rejected(tmp_path: Path, tag: str) -> None:
    marker = tmp_path / "version"
    marker.write_text(tag)
    with pytest.raises(ValueError, match="image version"):
        image_version(marker)


def test_authenticated_login_and_restored_session_report_image_tag(settings_factory, monkeypatch):
    monkeypatch.setattr("app.main.image_version", lambda: "9.8.7")
    config = settings_factory()
    with TestClient(create_app(config)) as client:
        assert client.get("/api/auth/session").status_code == 401
        response = client.post("/api/auth/login", json={"password": TEST_PASSWORD}, headers=ORIGIN)
        assert response.status_code == 200
        assert response.json()["image_version"] == "9.8.7"
        assert client.get("/api/auth/session").json()["image_version"] == "9.8.7"
        cookie = client.cookies[config.cookie_name]
    with TestClient(create_app(config)) as client:
        client.cookies.set(config.cookie_name, cookie)
        assert client.get("/api/auth/session").json()["image_version"] == "9.8.7"
