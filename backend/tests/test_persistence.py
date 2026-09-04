import asyncio
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import String, select
from sqlalchemy.orm import Mapped, mapped_column

from tuck_api.db import create_engine, create_session_factory, session_scope
from tuck_api.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PersistenceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "persistence_test_records"

    value: Mapped[str] = mapped_column(String(100))


def test_session_scope_commits_successful_transaction(isolated_database_url: str) -> None:
    async def exercise_transaction() -> tuple[PersistenceRecord, PersistenceRecord]:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            record = PersistenceRecord(value="committed")
            async with session_scope(factory) as session:
                session.add(record)

            async with factory() as session:
                stored = await session.scalar(
                    select(PersistenceRecord).where(PersistenceRecord.value == "committed")
                )
                assert stored is not None
                return record, stored
        finally:
            await engine.dispose()

    record, stored = asyncio.run(exercise_transaction())

    assert isinstance(record.id, UUID)
    assert isinstance(stored.created_at, datetime)
    assert stored.created_at.tzinfo is not None
    assert stored.updated_at.tzinfo is not None


def test_session_scope_rolls_back_failed_transaction(isolated_database_url: str) -> None:
    async def exercise_transaction() -> PersistenceRecord | None:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            try:
                async with session_scope(factory) as session:
                    session.add(PersistenceRecord(value="rolled back"))
                    await session.flush()
                    raise RuntimeError("force rollback")
            except RuntimeError:
                pass

            async with factory() as session:
                return cast(
                    PersistenceRecord | None,
                    await session.scalar(
                        select(PersistenceRecord).where(PersistenceRecord.value == "rolled back")
                    ),
                )
        finally:
            await engine.dispose()

    assert asyncio.run(exercise_transaction()) is None
