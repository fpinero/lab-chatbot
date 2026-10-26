import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.pool import NullPool

from app.config import Settings


def create_database(settings: Settings) -> Engine:
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    url = settings.database_url or f"sqlite:///{(settings.data_dir / 'lab.db').resolve()}"
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 10},
        poolclass=NullPool,
        hide_parameters=True,
    )

    @event.listens_for(engine, "connect")
    def pragmas(connection: sqlite3.Connection, record: object) -> None:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")

    return engine


def migrate(engine: Engine) -> None:
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
