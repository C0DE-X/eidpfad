"""Apply production migrations, including a safe baseline for older prototypes."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .database import Base, engine
from . import models as _models  # noqa: F401 - registers declarative metadata


def migrate() -> None:
    server_root = Path(__file__).resolve().parents[1]
    config = Config(str(server_root / "alembic.ini"))
    config.set_main_option("script_location", str(server_root / "migrations"))
    tables = set(inspect(engine).get_table_names())
    if tables and "alembic_version" not in tables:
        # Releases before 0.5 created their schema from SQLAlchemy metadata. Bring
        # missing additive tables in once, then establish the migration baseline.
        Base.metadata.create_all(bind=engine)
        command.stamp(config, "head")
    else:
        command.upgrade(config, "head")


if __name__ == "__main__":
    migrate()
