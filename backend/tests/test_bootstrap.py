from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from tests.conftest import TEST_PASSWORD

ORIGIN = {"Origin": "http://127.0.0.1:5173"}


def signin(client: TestClient) -> dict[str, str]:
    result = client.post("/api/auth/login", json={"password": TEST_PASSWORD}, headers=ORIGIN)
    assert result.status_code == 200, result.text
    return {**ORIGIN, "X-CSRF-Token": result.json()["csrf_token"]}


def test_mock_is_network_free(
    monkeypatch: pytest.MonkeyPatch, settings_factory: Callable[..., Settings]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Mock mode must never open a provider connection")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    with TestClient(create_app(settings_factory())) as client:
        assert client.get("/api/health/live").json() == {"status": "ok"}
        headers = signin(client)
        assert client.get("/api/dev/bootstrap").json()["simulated"] is True
        response = client.post("/api/dev/preview", json={"prompt": "Hello"}, headers=headers)
        assert response.json() == {
            "model": "mock/echo",
            "text": "Local preview: Hello",
            "simulated": True,
        }


def test_api_never_falls_back_to_html(
    tmp_path: Path, settings_factory: Callable[..., Settings]
) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>Application</html>")
    with TestClient(create_app(settings_factory(), static_dir=static)) as client:
        assert client.get("/conversation/example").text == "<html>Application</html>"
        headers = signin(client)
        for path in ("/api/unknown", "/api"):
            for method in ("GET", "POST", "PATCH", "DELETE", "PUT"):
                response = client.request(method, path, headers=headers)
                assert response.status_code == 404
                assert response.headers["content-type"] == "application/json"
                assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_invalid_input_is_sanitized(settings_factory: Callable[..., Settings]) -> None:
    with TestClient(create_app(settings_factory())) as client:
        headers = signin(client)
        response = client.post("/api/dev/preview", json={"prompt": "x" * 2001}, headers=headers)
        assert response.status_code == 422
        assert "x" * 100 not in response.text


def test_production_fails_closed(settings_factory: Callable[..., Settings]) -> None:
    with pytest.raises(ValidationError, match="Production requires"):
        settings_factory(app_env="production")
    with pytest.raises(ValidationError, match="Argon2id"):
        settings_factory(auth_password_hash="placeholder")  # noqa: S106, invalid fixture
    with pytest.raises(ValidationError, match="audience"):
        settings_factory(auth_mode="access", access_issuer="https://synthetic.cloudflareaccess.com")
    with pytest.raises(ValidationError):
        settings_factory(auth_mode="disabled")
