import time
from collections.abc import Callable

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt import PyJWKSet

from app.auth.access import AccessVerifier
from app.config import Settings
from app.main import create_app
from tests.test_bootstrap import ORIGIN


@pytest.fixture
def key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def configure_keys(verifier: AccessVerifier, key: rsa.RSAPrivateKey) -> None:
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk["kid"] = "synthetic-key"
    verifier.jwks.jwk_set_cache.put(PyJWKSet.from_dict({"keys": [jwk]}))


def make_token(key: rsa.RSAPrivateKey, **overrides: object) -> str:
    claims: dict[str, object] = {
        "sub": "synthetic-owner",
        "iss": "https://synthetic.cloudflareaccess.com",
        "aud": ["synthetic-audience"],
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "synthetic-key"})


def test_access_requires_valid_signature_issuer_audience_expiry_and_owner(
    key: rsa.RSAPrivateKey, settings_factory: Callable[..., Settings]
) -> None:
    config = settings_factory(
        auth_mode="access",
        access_issuer="https://synthetic.cloudflareaccess.com",
        access_audience="synthetic-audience",
        access_owner_subject="synthetic-owner",
    )
    verifier = AccessVerifier(config)
    configure_keys(verifier, key)
    assert verifier.verify(make_token(key))
    for overrides in (
        {"sub": "another-owner"},
        {"aud": "other"},
        {"iss": "https://evil.invalid"},
        {"exp": 1},
        {"iat": int(time.time()) + 3600},
    ):
        assert not verifier.verify(make_token(key, **overrides))
    assert not verifier.verify(
        make_token(rsa.generate_private_key(public_exponent=65537, key_size=2048))
    )
    assert not verifier.verify("malformed")


def test_access_checks_login_and_every_authenticated_request(
    key: rsa.RSAPrivateKey, settings_factory: Callable[..., Settings]
) -> None:
    config = settings_factory(
        auth_mode="access",
        access_issuer="https://synthetic.cloudflareaccess.com",
        access_audience="synthetic-audience",
        access_owner_subject="synthetic-owner",
    )
    app = create_app(config)
    with TestClient(app) as client:
        configure_keys(app.state.auth.access, key)
        assert client.get("/api/auth/login").status_code == 401
        assert client.post("/api/auth/login", headers=ORIGIN, json={}).status_code == 401
        headers = {**ORIGIN, "Cf-Access-Jwt-Assertion": make_token(key)}
        assert client.post("/api/auth/login", headers=headers, json={}).status_code == 200
        assert client.get("/api/auth/session", headers=headers).status_code == 200
        assert (
            client.get(
                "/api/auth/session",
                headers={"CF-Access-Authenticated-User-Email": "owner@example.invalid"},
            ).status_code
            == 401
        )


def test_jwks_rotation_refreshes_once_and_caches_new_key(
    key: rsa.RSAPrivateKey,
    settings_factory: Callable[..., Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = settings_factory(
        auth_mode="access",
        access_issuer="https://synthetic.cloudflareaccess.com",
        access_audience="synthetic-audience",
        access_owner_subject="synthetic-owner",
    )
    verifier = AccessVerifier(config)
    configure_keys(verifier, rsa.generate_private_key(public_exponent=65537, key_size=2048))
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk["kid"] = "rotated-synthetic-key"
    calls = []

    def fetch_keys():
        calls.append(True)
        return {"keys": [jwk]}

    monkeypatch.setattr(verifier.jwks, "fetch_data", fetch_keys)
    claims = jwt.decode(make_token(key), options={"verify_signature": False})
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "rotated-synthetic-key"})
    assert verifier.verify(token)
    assert verifier.verify(token)
    assert len(calls) == 1


def test_production_cookie_and_absence_of_mock_routes(
    key: rsa.RSAPrivateKey,
    settings_factory: Callable[..., Settings],
) -> None:
    config = settings_factory(
        app_env="production",
        app_origin="https://workspace.example.invalid",
        provider_mode="openrouter",
        auth_mode="access",
        access_issuer="https://synthetic.cloudflareaccess.com",
        access_audience="synthetic-audience",
        access_owner_subject="synthetic-owner",
    )
    app = create_app(config)
    with TestClient(app, base_url=config.app_origin) as client:
        configure_keys(app.state.auth.access, key)
        headers = {"Origin": config.app_origin, "Cf-Access-Jwt-Assertion": make_token(key)}
        response = client.post("/api/auth/login", json={}, headers=headers)
        cookie = response.headers["set-cookie"]
        assert cookie.startswith("__Host-lab-session=")
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
        assert "Path=/" in cookie and "Domain=" not in cookie
        assert client.get("/api/dev/bootstrap", headers=headers).status_code == 404
        schema = client.get("/openapi.json")
        assert schema.status_code == 404 or schema.headers["content-type"].startswith("text/html")
        assert "strict-transport-security" in response.headers
