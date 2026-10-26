import json
from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table

from app.config import Settings
from app.db import create_database
from app.main import create_app
from tests.test_bootstrap import signin


def test_populated_m2_database_upgrades_without_detaching_usage(
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory()
    engine = create_database(settings)
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0002")
        metadata = MetaData()
        owners = Table("owners", metadata, autoload_with=connection)
        conversations = Table("conversations", metadata, autoload_with=connection)
        runs = Table("runs", metadata, autoload_with=connection)
        charges = Table("usage_ledger", metadata, autoload_with=connection)
        connection.execute(owners.insert().values(id="primary", created_at=1))
        connection.execute(
            conversations.insert().values(
                id="legacy-conversation",
                owner_id="primary",
                title="Legacy evidence",
                created_at=1,
                updated_at=1,
                head_run_id="legacy-run",
            )
        )
        connection.execute(
            runs.insert().values(
                id="legacy-run",
                owner_id="primary",
                conversation_id="legacy-conversation",
                model_id="synthetic/model",
                turn=1,
                snapshot_json='[{"role":"user","content":"Legacy prompt"}]',
                settings_json=json.dumps({"model_name": "Synthetic", "simulated": True}),
                prompt="Legacy prompt",
                output="Legacy answer",
                status="succeeded",
                sequence=1,
                created_at=1,
            )
        )
        connection.execute(
            charges.insert().values(
                id="legacy-charge",
                owner_id="primary",
                idempotency_key="legacy-submission",
                request_hash="0" * 64,
                run_id="legacy-run",
                state="settled",
                reserved_microusd=9,
                actual_microusd=7,
                purpose="generation",
                price_json='{"prompt":"0"}',
                created_at=1,
            )
        )
    engine.dispose()
    with TestClient(create_app(settings)) as client:
        signin(client)
        result = client.get("/api/conversations/legacy-conversation")
        assert result.status_code == 200, result.text
        assert result.json()["runs"][0]["output"] == "Legacy answer"
        assert result.json()["runs"][0]["actual_microusd"] == 7
