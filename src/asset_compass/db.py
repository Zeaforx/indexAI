"""Database connection and schema initialization."""

import os
from pathlib import Path
from collections.abc import Iterator
from contextlib import contextmanager

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

def db_url() -> str:
    return os.environ.get("ASSET_COMPASS_DB_URL", "sqlite:///./catalog.sqlite3")


def make_engine(url: str | None = None) -> Engine:
    url = url or db_url()
    if url.startswith("sqlite:"):
        engine = create_engine(url, connect_args={"timeout": 15})

        @event.listens_for(engine, "connect")
        def _sqlite_setup(connection, _record) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.close()
    else:
        engine = create_engine(url, pool_pre_ping=True)
    return engine


def initialize(engine: Engine) -> None:
    """Upgrade through reproducible, versioned Alembic migrations."""
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@contextmanager
def open_session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        yield session

