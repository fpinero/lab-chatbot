"""Export the backend contract without publishing runtime configuration."""

import json
import sys
from pathlib import Path

from argon2 import PasswordHasher

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings
from app.main import create_app

print(
    json.dumps(
        create_app(
            Settings(
                app_env="test",
                auth_password_hash=PasswordHasher().hash(
                    "synthetic-contract-passphrase"
                ),
                auth_password_hash_file=None,
                auth_policy_file=None,
            )
        ).openapi()
    )
)
