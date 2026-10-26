from ipaddress import ip_network
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from argon2 import PasswordHasher, Type, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "production"] = "development"
    app_origin: str = "http://127.0.0.1:5173"
    provider_mode: Literal["mock", "openrouter"] = "mock"
    data_dir: Path = Path("data")
    database_url: str | None = None
    auth_mode: Literal["password", "access", "policy"] = "password"
    auth_password_hash: SecretStr = SecretStr("")
    auth_password_hash_file: Path | None = None
    auth_policy_file: Path | None = None
    access_issuer: str = ""
    access_audience: str = ""
    access_owner_subject: str = ""
    session_idle_seconds: int = Field(default=1800, ge=1, le=43200)
    session_absolute_seconds: int = Field(default=43200, ge=1, le=604800)
    trusted_proxy_networks: list[str] = Field(default_factory=list)

    @property
    def production(self) -> bool:
        return self.app_env == "production"

    @property
    def cookie_name(self) -> str:
        return "__Host-lab-session" if self.production else "lab-dev-session"

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        origin = urlsplit(self.app_origin)
        if origin.scheme not in {"http", "https"} or not origin.hostname or origin.path:
            raise ValueError("APP_ORIGIN must be an exact origin without a path.")
        if origin.query or origin.fragment or origin.username or origin.password:
            raise ValueError("APP_ORIGIN must not contain credentials or URL parameters.")
        if (
            not self.production
            and self.app_env != "test"
            and origin.hostname not in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError("Development requires a loopback origin.")
        if self.production:
            if (
                origin.scheme != "https"
                or self.provider_mode == "mock"
                or self.auth_mode == "policy"
            ):
                raise ValueError("Production requires HTTPS, a live provider and secure identity.")
        if self.auth_password_hash_file:
            self.auth_password_hash = SecretStr(self.auth_password_hash_file.read_text().strip())
        if self.auth_mode == "password":
            try:
                params = extract_parameters(self.auth_password_hash.get_secret_value())
            except (InvalidHashError, ValueError) as exc:
                raise ValueError("Configure a valid owner Argon2id password hash.") from exc
            if params.type != Type.ID or params.memory_cost < 65536 or params.time_cost < 3:
                raise ValueError("The owner hash must use Argon2id with adequate parameters.")
        if self.production and self.auth_mode == "password":
            for placeholder in (
                "password",
                "changeme",
                "synthetic-unit-passphrase",
                "synthetic-browser-passphrase",
                "synthetic-contract-passphrase",
            ):
                try:
                    PasswordHasher().verify(self.auth_password_hash.get_secret_value(), placeholder)
                except VerificationError:
                    continue
                raise ValueError("Production rejects sample and placeholder credentials.")
        if (
            self.production
            and self.auth_policy_file
            and self.auth_policy_file.stat().st_mode & 0o222
        ):
            raise ValueError("Production policy files must be mounted read-only.")
        if self.auth_mode == "access":
            issuer = urlsplit(self.access_issuer)
            if (
                issuer.scheme != "https"
                or not issuer.hostname
                or not issuer.hostname.endswith(".cloudflareaccess.com")
                or issuer.path
                or issuer.query
                or issuer.fragment
                or issuer.username
                or issuer.port
            ):
                raise ValueError("Configure the official Access team issuer origin.")
            if not self.access_audience.strip() or not self.access_owner_subject.strip():
                raise ValueError("Configure an Access audience and allowed owner subject.")
        if self.auth_mode == "policy" and not self.auth_policy_file:
            raise ValueError("Local policy mode requires an explicit private policy file.")
        for network in self.trusted_proxy_networks:
            ip_network(network)
        if self.database_url and not self.database_url.startswith("sqlite:///"):
            raise ValueError("Only local SQLite databases are supported.")
        return self
