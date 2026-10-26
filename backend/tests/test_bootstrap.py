from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def test_mock_is_network_free(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Mock mode must never open a provider connection")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    with TestClient(create_app(Settings(app_env="test"))) as client:
        assert client.get("/api/health/live").json() == {"status": "ok"}
        assert client.get("/api/dev/bootstrap").json()["simulated"] is True
        response = client.post("/api/dev/preview", json={"prompt": "Hello"})
        assert response.json() == {
            "model": "mock/echo",
            "text": "Local preview: Hello",
            "simulated": True,
        }


def test_api_never_falls_back_to_html(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>Application</html>")
    with TestClient(create_app(Settings(app_env="test"), static_dir=tmp_path)) as client:
        assert client.get("/conversation/example").text == "<html>Application</html>"
        for method in ("GET", "POST", "PATCH", "DELETE", "PUT"):
            response = client.request(method, "/api/unknown")
            assert response.status_code == 404
            assert response.headers["content-type"] == "application/json"
            assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_invalid_input_is_sanitized() -> None:
    with TestClient(create_app(Settings(app_env="test"))) as client:
        response = client.post("/api/dev/preview", json={"prompt": "x" * 2001})
        assert response.status_code == 422
        assert "x" * 100 not in response.text


def test_bootstrap_fails_closed() -> None:
    with pytest.raises(ValidationError, match="Production is unavailable"):
        Settings(app_env="production")
    with pytest.raises(ValidationError, match="Live providers are unavailable"):
        Settings(provider_mode="openrouter")
