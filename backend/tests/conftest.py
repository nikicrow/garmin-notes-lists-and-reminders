import asyncio
import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
def isolated_database_url() -> Iterator[str]:
    admin_url = os.getenv(
        "TUCK_TEST_ADMIN_DATABASE_URL",
        "postgresql://tuck:local-development-only@localhost:5432/postgres",
    )
    database_name = f"tuck_test_{uuid4().hex}"
    sqlalchemy_admin_url = admin_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    async def create_database() -> None:
        engine = create_async_engine(sqlalchemy_admin_url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        finally:
            await engine.dispose()

    async def drop_database() -> None:
        engine = create_async_engine(sqlalchemy_admin_url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                await connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                    ),
                    {"database_name": database_name},
                )
                await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        finally:
            await engine.dispose()

    asyncio.run(create_database())
    try:
        database_url = admin_url.rsplit("/", 1)[0] + f"/{database_name}"
        yield database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    finally:
        asyncio.run(drop_database())
