import asyncio
from pathlib import Path
from typing import cast

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from pytest import MonkeyPatch
from sqlalchemy import MetaData, text

from tuck_api import schema
from tuck_api.db import create_engine

BACKEND_ROOT = Path(__file__).parents[1]


def test_migrations_upgrade_clean_postgresql_database(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    config = Config(BACKEND_ROOT / "alembic.ini")
    monkeypatch.setenv("TUCK_DATABASE_URL", isolated_database_url)

    command.upgrade(config, "head")

    expected_metadata = MetaData(naming_convention=schema.metadata.naming_convention)
    for table in schema.application_tables:
        table.to_metadata(expected_metadata)

    async def read_migration_state() -> tuple[str | None, set[str], list[object]]:
        engine = create_engine(isolated_database_url)
        try:
            async with engine.connect() as connection:
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                rows = await connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
                schema_differences = await connection.run_sync(
                    lambda sync_connection: compare_metadata(
                        MigrationContext.configure(sync_connection), expected_metadata
                    )
                )
                return cast(str | None, revision), set(rows.scalars()), schema_differences
        finally:
            await engine.dispose()

    revision, tables, schema_differences = asyncio.run(read_migration_state())

    assert revision == "0007_notification_foundation"
    assert {
        "users",
        "user_sessions",
        "notes",
        "lists",
        "resource_memberships",
        "list_items",
        "reminders",
        "push_subscriptions",
        "reminder_recipients",
        "notification_deliveries",
    } <= tables
    assert schema_differences == []

    command.downgrade(config, "0006_one_time_reminders")

    downgraded_revision, downgraded_tables, _ = asyncio.run(read_migration_state())
    assert downgraded_revision == "0006_one_time_reminders"
    assert {
        "push_subscriptions",
        "reminder_recipients",
        "notification_deliveries",
    }.isdisjoint(downgraded_tables)
