"""Start an isolated, authenticated backend for browser tests only."""

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from argon2 import PasswordHasher

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings
from app.main import create_app

with TemporaryDirectory(prefix="lab-browser-") as directory:
    if os.environ.get("APP_ENV") == "production":
        raise SystemExit("Browser fixtures are not allowed in production.")
    config = Settings(
        app_env="test",
        auth_mode="password",
        provider_mode="mock",
        app_origin=f"http://127.0.0.1:{int(os.environ.get('LAB_BROWSER_UI_PORT', '5173'))}",
        auth_password_hash=PasswordHasher().hash("synthetic-browser-passphrase"),
        data_dir=Path(directory),
        database_url=None,
        auth_password_hash_file=None,
        auth_policy_file=None,
    )
    uvicorn.run(
        create_app(config),
        host="127.0.0.1",
        port=int(os.environ.get("LAB_BROWSER_API_PORT", "8000")),
        proxy_headers=False,
        access_log=False,
    )
