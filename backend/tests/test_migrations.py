import asyncio
from pathlib import Path
from typing import cast

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tuck_api.db import create_engine

BACKEND_ROOT = Path(__file__).parents[1]


def test_migrations_upgrade_clean_postgresql_database(isolated_database_url: str) -> None:
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)

    command.upgrade(config, "head")

    async def read_revision() -> str | None:
        engine = create_engine(isolated_database_url)
        try:
            async with engine.connect() as connection:
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                return cast(str | None, revision)
        finally:
            await engine.dispose()

    assert asyncio.run(read_revision()) == "0001_initial_infrastructure"
