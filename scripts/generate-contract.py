"""Export the backend contract without publishing runtime configuration."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

print(json.dumps(create_app(Settings(app_env="test")).openapi()))
