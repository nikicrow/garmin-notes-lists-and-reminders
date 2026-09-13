import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from tuck_api.db import create_engine, create_session_factory, session_scope
from tuck_api.models import Base, NotificationDelivery, Reminder, ReminderRecipient, User
from tuck_api.notification_deliveries import claim_due_deliveries, materialize_due_deliveries
from tuck_api.security import hash_password


def test_duplicate_delivery_materialization_is_harmless(isolated_database_url: str) -> None:
    now = datetime.now(UTC)

    async def exercise() -> tuple[int, int, list[NotificationDelivery]]:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_scope(factory) as database:
                recipient = User(
                    id=uuid4(), username="niki", password_hash=hash_password("password")
                )
                database.add(recipient)
                await database.flush()
                reminder = Reminder(
                    creator_user_id=recipient.id,
                    title="Appointment",
                    detail=None,
                    due_at_utc=now - timedelta(minutes=1),
                    source_timezone="Australia/Brisbane",
                    is_urgent=False,
                )
                reminder.recipient_links = [ReminderRecipient(user_id=recipient.id)]
                database.add(reminder)
                await database.flush()

            async with session_scope(factory) as database:
                first_count = await materialize_due_deliveries(database, now=now)
            async with session_scope(factory) as database:
                second_count = await materialize_due_deliveries(database, now=now)
            async with factory() as database:
                deliveries = list(await database.scalars(select(NotificationDelivery)))
            return first_count, second_count, deliveries
        finally:
            await engine.dispose()

    first_count, second_count, deliveries = asyncio.run(exercise())

    assert (first_count, second_count) == (1, 0)
    assert len(deliveries) == 1
    assert deliveries[0].status == "pending"
    assert deliveries[0].attempt_count == 0
    assert deliveries[0].next_attempt_at == now


def test_concurrent_claimers_cannot_own_the_same_delivery(isolated_database_url: str) -> None:
    now = datetime.now(UTC)

    async def exercise() -> tuple[list[NotificationDelivery], list[NotificationDelivery]]:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with session_scope(factory) as database:
                recipient = User(
                    id=uuid4(), username="niki", password_hash=hash_password("password")
                )
                database.add(recipient)
                await database.flush()
                reminder = Reminder(
                    creator_user_id=recipient.id,
                    title="Appointment",
                    detail=None,
                    due_at_utc=now - timedelta(minutes=1),
                    source_timezone="Australia/Brisbane",
                    is_urgent=False,
                )
                reminder.recipient_links = [ReminderRecipient(user_id=recipient.id)]
                database.add(reminder)
                await database.flush()
                assert await materialize_due_deliveries(database, now=now) == 1

            async def claim(worker_id: str) -> list[NotificationDelivery]:
                async with session_scope(factory) as database:
                    return await claim_due_deliveries(
                        database,
                        worker_id=worker_id,
                        now=now,
                        lease_duration=timedelta(minutes=5),
                        limit=1,
                    )

            first, second = await asyncio.gather(claim("worker-1"), claim("worker-2"))
            return first, second
        finally:
            await engine.dispose()

    first, second = asyncio.run(exercise())

    claimed = first + second
    assert len(claimed) == 1
    assert claimed[0].status == "claimed"
    assert claimed[0].claimed_by in {"worker-1", "worker-2"}
    assert claimed[0].attempt_count == 1
    assert claimed[0].claimed_at == now


def test_expired_claim_recovers_after_worker_restart(isolated_database_url: str) -> None:
    first_claim_at = datetime.now(UTC)
    recovered_at = first_claim_at + timedelta(minutes=6)

    async def seed_and_claim() -> NotificationDelivery:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with session_scope(factory) as database:
                recipient = User(
                    id=uuid4(), username="niki", password_hash=hash_password("password")
                )
                database.add(recipient)
                await database.flush()
                reminder = Reminder(
                    creator_user_id=recipient.id,
                    title="Appointment",
                    detail=None,
                    due_at_utc=first_claim_at - timedelta(minutes=1),
                    source_timezone="Australia/Brisbane",
                    is_urgent=False,
                )
                reminder.recipient_links = [ReminderRecipient(user_id=recipient.id)]
                database.add(reminder)
                await database.flush()
                assert await materialize_due_deliveries(database, now=first_claim_at) == 1
            async with session_scope(factory) as database:
                return (
                    await claim_due_deliveries(
                        database,
                        worker_id="worker-before-restart",
                        now=first_claim_at,
                        lease_duration=timedelta(minutes=5),
                        limit=1,
                    )
                )[0]
        finally:
            await engine.dispose()

    async def recover_after_restart() -> NotificationDelivery:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as database:
                recovered = await claim_due_deliveries(
                    database,
                    worker_id="worker-after-restart",
                    now=recovered_at,
                    lease_duration=timedelta(minutes=5),
                    limit=1,
                )
                assert len(recovered) == 1
                return recovered[0]
        finally:
            await engine.dispose()

    original = asyncio.run(seed_and_claim())
    recovered = asyncio.run(recover_after_restart())

    assert recovered.id == original.id
    assert recovered.status == "claimed"
    assert recovered.claimed_by == "worker-after-restart"
    assert recovered.claimed_at == recovered_at
    assert recovered.attempt_count == 2
