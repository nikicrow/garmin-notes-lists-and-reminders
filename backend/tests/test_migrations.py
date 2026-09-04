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

    async def read_migration_state() -> tuple[str | None, set[str]]:
        engine = create_engine(isolated_database_url)
        try:
            async with engine.connect() as connection:
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                rows = await connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
                return cast(str | None, revision), set(rows.scalars())
        finally:
            await engine.dispose()

    revision, tables = asyncio.run(read_migration_state())

    assert revision == "0002_user_accounts"
    assert {"users", "user_sessions"} <= tables
