from decimal import Decimal
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
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_api_key_file: Path | None = None
    max_request_usd: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    live_test_budget_usd: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    daily_budget_usd: Decimal = Field(default=Decimal("0"), ge=0, le=1000)
    model_price_ceiling_per_million: Decimal = Field(default=Decimal("10"), ge=0, le=1000)
    model_allowlist: list[str] = Field(default_factory=list)
    max_output_tokens: int = Field(default=2048, ge=1, le=32768)
    max_queued_runs: int = Field(default=16, ge=1, le=64)
    max_upload_files: int = Field(default=5, ge=1, le=10)
    max_upload_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)
    max_upload_total_bytes: int = Field(default=25 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    max_pdf_pages: int = Field(default=50, ge=1, le=200)
    max_document_characters: int = Field(default=100000, ge=1, le=500000)
    max_image_pixels: int = Field(default=20000000, ge=1, le=40000000)
    max_image_edge: int = Field(default=2048, ge=16, le=4096)
    max_provider_payload_bytes: int = Field(default=32 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024)
    storage_ceiling_bytes: int = Field(default=5 * 1024**3, ge=1024 * 1024)
    vision_request_allowance_usd: Decimal = Field(default=Decimal("0"), ge=0, le=100)
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
        if self.openrouter_api_key_file:
            self.openrouter_api_key = SecretStr(self.openrouter_api_key_file.read_text().strip())
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
