from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from argon2 import PasswordHasher
from pydantic import SecretStr

from app.config import Settings

TEST_PASSWORD = "synthetic-unit-passphrase"  # noqa: S105, synthetic fixture


@pytest.fixture(scope="session")
def password_hash() -> SecretStr:
    return SecretStr(PasswordHasher().hash(TEST_PASSWORD))


@pytest.fixture
def settings_factory(tmp_path: Path, password_hash: SecretStr) -> Callable[..., Settings]:
    def build(**overrides: Any) -> Settings:
        values = dict(
            app_env="test",
            auth_mode="password",
            provider_mode="mock",
            data_dir=tmp_path / "data",
            auth_password_hash=password_hash,
            auth_password_hash_file=None,
            auth_policy_file=None,
            database_url=None,
        )
        values.update(overrides)
        return Settings(**values)

    return build
