from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.service import digest
from app.config import Settings
from app.main import create_app
from app.models import OwnerSession
from tests.conftest import TEST_PASSWORD
from tests.test_bootstrap import ORIGIN, signin


@pytest.mark.parametrize(
    "path",
    [
        "/api/conversations",
        "/api/attachments/id",
        "/api/media/id",
        "/api/usage",
        "/api/runs/id",
        "/api/runs/id/events",
        "/api/conversations/id/export",
        "/api/dev/preview",
    ],
)
def test_private_families_deny_anonymous(
    path: str, settings_factory: Callable[..., Settings]
) -> None:
    with TestClient(create_app(settings_factory())) as client:
        response = client.get(path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "session_required"


def test_login_origin_csrf_rotation_logout(settings_factory: Callable[..., Settings]) -> None:
    config = settings_factory()
    app = create_app(config)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"password": TEST_PASSWORD}).status_code == 403
        assert (
            client.post(
                "/api/auth/login",
                json={"password": TEST_PASSWORD},
                headers={"Origin": "https://evil.invalid"},
            ).status_code
            == 403
        )
        csrf = signin(client)
        cookie = client.cookies[config.cookie_name]
        response = client.get("/api/auth/session")
        assert response.json()["owner_id"] == "primary"
        assert (
            "HttpOnly"
            in client.post(
                "/api/auth/login", json={"password": TEST_PASSWORD}, headers=ORIGIN
            ).headers["set-cookie"]
        )
        assert client.cookies[config.cookie_name] != cookie
        assert client.post("/api/auth/logout", headers=csrf).status_code == 403
        assert (
            client.post("/api/dev/preview", json={"prompt": "hello"}, headers=ORIGIN).status_code
            == 403
        )
        current = client.get("/api/auth/session").json()
        assert (
            client.post(
                "/api/auth/logout", headers={**ORIGIN, "X-CSRF-Token": current["csrf_token"]}
            ).status_code
            == 204
        )
        assert client.get("/api/auth/session").status_code == 401
        client.cookies.set(config.cookie_name, cookie)
        assert client.get("/api/auth/session").status_code == 401


def test_only_token_hash_is_stored_and_session_survives_restart(
    settings_factory: Callable[..., Settings],
) -> None:
    config = settings_factory()
    app = create_app(config)
    with TestClient(app) as client:
        signin(client)
        token = client.cookies[config.cookie_name]
        with Session(app.state.auth.engine) as db:
            record = db.scalar(select(OwnerSession))
            assert record and record.token_hash == digest(token) and record.token_hash != token
            assert db.execute(text("PRAGMA journal_mode")).scalar() == "wal"
            assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1
            assert db.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002"
    with TestClient(create_app(config)) as client:
        client.cookies.set(config.cookie_name, token)
        assert client.get("/api/auth/session").json()["owner_id"] == "primary"


def test_idle_and_absolute_expiry(settings_factory: Callable[..., Settings]) -> None:
    now = datetime(2031, 7, 1, tzinfo=UTC)
    app = create_app(
        settings_factory(session_idle_seconds=30, session_absolute_seconds=60), clock=lambda: now
    )
    with TestClient(app) as client:
        signin(client)
        now += timedelta(seconds=20)
        assert client.get("/api/auth/session").status_code == 200
        now += timedelta(seconds=20)
        assert client.get("/api/auth/session").status_code == 200
        now += timedelta(seconds=20)
        assert client.get("/api/auth/session").status_code == 401
        signin(client)
        now += timedelta(seconds=30)
        assert client.get("/api/auth/session").status_code == 401


def test_failed_attempts_survive_restart_and_ignore_forged_proxy_headers(
    settings_factory: Callable[..., Settings],
) -> None:
    config = settings_factory()
    with TestClient(create_app(config)) as client:
        for attempt in range(5):
            response = client.post(
                "/api/auth/login",
                headers={
                    **ORIGIN,
                    "X-Forwarded-For": f"192.0.2.{attempt}",
                    "CF-Connecting-IP": f"192.0.2.{attempt}",
                },
                json={"password": "incorrect"},
            )
            assert response.status_code == 401
    with TestClient(create_app(config)) as client:
        response = client.post("/api/auth/login", headers=ORIGIN, json={"password": TEST_PASSWORD})
        assert response.status_code == 429
        assert response.headers["retry-after"] == "300"


def test_throttle_window_expires(settings_factory: Callable[..., Settings]) -> None:
    now = datetime(2031, 1, 1, tzinfo=UTC)
    with TestClient(create_app(settings_factory(), clock=lambda: now)) as client:
        for _ in range(5):
            assert (
                client.post(
                    "/api/auth/login", headers=ORIGIN, json={"password": "incorrect"}
                ).status_code
                == 401
            )
        now += timedelta(seconds=300)
        signin(client)


def test_cross_site_reads_and_forged_identity_fail(
    settings_factory: Callable[..., Settings],
) -> None:
    with TestClient(create_app(settings_factory())) as client:
        signin(client)
        assert (
            client.get("/api/auth/session", headers={"Origin": "https://evil.invalid"}).status_code
            == 403
        )
        assert (
            client.get("/api/auth/session", headers={"Sec-Fetch-Site": "cross-site"}).status_code
            == 403
        )
        client.cookies.clear()
        assert (
            client.get(
                "/api/auth/session",
                headers={"CF-Access-Authenticated-User-Email": "owner@example.invalid"},
            ).status_code
            == 401
        )


def test_actual_body_limit_precedes_json_parsing(settings_factory: Callable[..., Settings]) -> None:
    with TestClient(create_app(settings_factory())) as client:
        response = client.post(
            "/api/auth/login",
            content=(b"x" * 40000 for _ in range(2)),
            headers={**ORIGIN, "Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "body_too_large"
        assert "x" * 100 not in response.text


def test_trusted_proxy_chain_stops_at_first_untrusted_hop(
    settings_factory: Callable[..., Settings],
) -> None:
    from starlette.requests import Request

    app = create_app(settings_factory(trusted_proxy_networks=["10.0.0.0/8"]))
    with TestClient(app):
        request = Request(
            {
                "type": "http",
                "client": ("10.1.0.1", 1234),
                "headers": [(b"x-forwarded-for", b"192.0.2.99, 198.51.100.7, 10.2.0.1")],
            }
        )
        assert app.state.auth.client_ip(request) == "198.51.100.7"
        direct = Request(
            {
                "type": "http",
                "client": ("198.51.100.8", 1234),
                "headers": [(b"x-forwarded-for", b"192.0.2.99")],
            }
        )
        assert app.state.auth.client_ip(direct) == "198.51.100.8"


def test_generic_optional_policy_is_additive_and_does_not_expire_sessions(
    settings_factory: Callable[..., Settings],
    tmp_path,
) -> None:
    path = tmp_path / "synthetic.json"
    path.write_text('{"timezone":"Pacific/Auckland","template":"%Y-%j"}')
    now = datetime(2032, 1, 1, 10, 59, 59, tzinfo=UTC)
    app = create_app(settings_factory(auth_policy_file=path), clock=lambda: now)
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/auth/login",
                headers=ORIGIN,
                json={"password": TEST_PASSWORD, "code": "invalid"},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/auth/login",
                headers=ORIGIN,
                json={"password": "incorrect", "code": "2032-001"},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/auth/login",
                headers=ORIGIN,
                json={"password": TEST_PASSWORD, "code": "2032-001"},
            ).status_code
            == 200
        )
        now += timedelta(seconds=1)
        assert client.get("/api/auth/session").status_code == 200


def test_production_rejects_placeholder_password_hash(
    settings_factory: Callable[..., Settings],
) -> None:
    from argon2 import PasswordHasher
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="placeholder"):
        settings_factory(
            app_env="production",
            app_origin="https://workspace.example.invalid",
            provider_mode="openrouter",
            auth_password_hash=PasswordHasher().hash("password"),
        )
