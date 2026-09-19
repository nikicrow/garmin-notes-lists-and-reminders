import asyncio
from collections import deque
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tuck_api.db import create_engine, create_session_factory, session_scope
from tuck_api.models import (
    Base,
    NotificationDelivery,
    PushSubscription,
    Reminder,
    ReminderRecipient,
    User,
)
from tuck_api.notification_deliveries import claim_due_deliveries, materialize_due_deliveries
from tuck_api.notification_worker import run_worker_once
from tuck_api.security import hash_password
from tuck_api.web_push import NotificationPayload, PushOutcome, PushResult, PushSubscriptionData


class ScriptedGateway:
    def __init__(self, results: dict[str, Sequence[PushResult | BaseException]]) -> None:
        self.results = {
            endpoint: deque(endpoint_results) for endpoint, endpoint_results in results.items()
        }
        self.calls: list[str] = []
        self.confirmed_successes: list[str] = []

    def send(self, subscription: PushSubscriptionData, payload: NotificationPayload) -> PushResult:
        endpoint = subscription["endpoint"]
        self.calls.append(endpoint)
        result = self.results[endpoint].popleft()
        if isinstance(result, BaseException):
            raise result
        if result.outcome == PushOutcome.SUCCESS:
            self.confirmed_successes.append(endpoint)
        return result


async def seed_due_reminder(
    factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    usernames: Sequence[str],
    subscription_expiries: dict[str, datetime | None] | None = None,
) -> tuple[UUID, dict[str, UUID]]:
    async with session_scope(factory) as database:
        users = {
            username: User(id=uuid4(), username=username, password_hash=hash_password("password"))
            for username in usernames
        }
        database.add_all(users.values())
        await database.flush()
        reminder = Reminder(
            creator_user_id=users[usernames[0]].id,
            title="Private reminder",
            detail="Private detail",
            due_at_utc=now - timedelta(minutes=1),
            source_timezone="Australia/Brisbane",
            is_urgent=False,
        )
        reminder.recipient_links = [
            ReminderRecipient(user_id=users[username].id) for username in usernames
        ]
        database.add(reminder)
        for endpoint, expires_at in (subscription_expiries or {}).items():
            username = endpoint.split("-", 1)[0]
            database.add(
                PushSubscription(
                    user_id=users[username].id,
                    endpoint=endpoint,
                    p256dh="public-key",
                    auth="auth-secret",
                    expires_at=expires_at,
                )
            )
        await database.flush()
        return reminder.id, {username: user.id for username, user in users.items()}


def test_concurrent_workers_deliver_once_to_each_active_recipient(
    isolated_database_url: str,
) -> None:
    now = datetime.now(UTC)
    gateway = ScriptedGateway(
        {
            "niki-active": [
                PushResult(PushOutcome.TRANSIENT, "http_503"),
                PushResult.success(),
            ],
            "ben-active": [PushResult.success()],
            "ben-gone": [PushResult(PushOutcome.EXPIRED, "http_410")],
            "ben-stale": [],
        }
    )

    async def exercise() -> tuple[list[NotificationDelivery], list[PushSubscription]]:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            reminder_id, _ = await seed_due_reminder(
                factory,
                now=now,
                usernames=["niki", "ben"],
                subscription_expiries={
                    "niki-active": None,
                    "ben-active": None,
                    "ben-gone": None,
                    "ben-stale": now - timedelta(seconds=1),
                },
            )

            first_passes = await asyncio.gather(
                run_worker_once(
                    factory,
                    gateway=gateway,
                    worker_id="worker-a",
                    now=now,
                    lease_duration=timedelta(minutes=5),
                    batch_size=10,
                    max_attempts=3,
                ),
                run_worker_once(
                    factory,
                    gateway=gateway,
                    worker_id="worker-b",
                    now=now,
                    lease_duration=timedelta(minutes=5),
                    batch_size=10,
                    max_attempts=3,
                ),
            )
            assert sum(result.materialized for result in first_passes) == 2
            assert sum(result.claimed for result in first_passes) == 2
            assert sum(result.sent for result in first_passes) == 1
            assert sum(result.retryable for result in first_passes) == 1

            retry_at = now + timedelta(seconds=30)
            retry = await run_worker_once(
                factory,
                gateway=gateway,
                worker_id="worker-c",
                now=retry_at,
                lease_duration=timedelta(minutes=5),
                batch_size=10,
                max_attempts=3,
            )
            assert retry.sent == 1

            duplicate_passes = await asyncio.gather(
                run_worker_once(
                    factory,
                    gateway=gateway,
                    worker_id="worker-d",
                    now=retry_at,
                    lease_duration=timedelta(minutes=5),
                    batch_size=10,
                    max_attempts=3,
                ),
                run_worker_once(
                    factory,
                    gateway=gateway,
                    worker_id="worker-e",
                    now=retry_at,
                    lease_duration=timedelta(minutes=5),
                    batch_size=10,
                    max_attempts=3,
                ),
            )
            assert sum(result.claimed for result in duplicate_passes) == 0

            async with factory() as database:
                deliveries = list(
                    await database.scalars(
                        select(NotificationDelivery)
                        .where(NotificationDelivery.reminder_id == reminder_id)
                        .order_by(NotificationDelivery.recipient_user_id)
                    )
                )
                subscriptions = list(await database.scalars(select(PushSubscription)))
                return deliveries, subscriptions
        finally:
            await engine.dispose()

    deliveries, subscriptions = asyncio.run(exercise())

    assert len(deliveries) == 2
    assert {delivery.status for delivery in deliveries} == {"sent"}
    assert sorted(delivery.attempt_count for delivery in deliveries) == [1, 2]
    assert all(delivery.sent_at is not None for delivery in deliveries)
    assert gateway.calls.count("niki-active") == 2
    assert gateway.calls.count("ben-active") == 1
    assert gateway.calls.count("ben-gone") == 1
    assert "ben-stale" not in gateway.calls
    subscriptions_by_endpoint = {
        subscription.endpoint: subscription for subscription in subscriptions
    }
    assert subscriptions_by_endpoint["ben-gone"].disabled_at == now
    assert subscriptions_by_endpoint["ben-active"].disabled_at is None
    assert subscriptions_by_endpoint["ben-stale"].disabled_at is None


def test_expired_claim_is_delivered_once_after_worker_restart(
    isolated_database_url: str,
) -> None:
    claimed_at = datetime.now(UTC)
    recovered_at = claimed_at + timedelta(minutes=5, seconds=1)
    gateway = ScriptedGateway({"niki-active": [PushResult.success()]})

    async def exercise() -> NotificationDelivery:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            reminder_id, _ = await seed_due_reminder(
                factory,
                now=claimed_at,
                usernames=["niki"],
                subscription_expiries={"niki-active": None},
            )
            async with session_scope(factory) as database:
                assert await materialize_due_deliveries(database, now=claimed_at) == 1
            async with session_scope(factory) as database:
                claimed = await claim_due_deliveries(
                    database,
                    worker_id="worker-before-crash",
                    now=claimed_at,
                    lease_duration=timedelta(minutes=5),
                    limit=10,
                )
                assert len(claimed) == 1

            recovered = await run_worker_once(
                factory,
                gateway=gateway,
                worker_id="worker-after-restart",
                now=recovered_at,
                lease_duration=timedelta(minutes=5),
                batch_size=10,
                max_attempts=3,
            )
            assert recovered.sent == 1
            duplicate = await run_worker_once(
                factory,
                gateway=gateway,
                worker_id="worker-after-restart",
                now=recovered_at,
                lease_duration=timedelta(minutes=5),
                batch_size=10,
                max_attempts=3,
            )
            assert duplicate.claimed == 0
            async with factory() as database:
                delivery = await database.scalar(
                    select(NotificationDelivery).where(
                        NotificationDelivery.reminder_id == reminder_id
                    )
                )
                assert delivery is not None
                return delivery
        finally:
            await engine.dispose()

    delivery = asyncio.run(exercise())

    assert delivery.status == "sent"
    assert delivery.attempt_count == 2
    assert delivery.sent_at == recovered_at
    assert gateway.calls == ["niki-active"]


def test_provider_timeout_retries_to_one_observable_success(
    isolated_database_url: str,
) -> None:
    now = datetime.now(UTC)
    gateway = ScriptedGateway(
        {
            "niki-active": [
                TimeoutError("response lost after provider accepted request"),
                PushResult.success(),
            ]
        }
    )

    async def exercise() -> NotificationDelivery:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            reminder_id, _ = await seed_due_reminder(
                factory,
                now=now,
                usernames=["niki"],
                subscription_expiries={"niki-active": None},
            )
            first = await run_worker_once(
                factory,
                gateway=gateway,
                worker_id="worker-a",
                now=now,
                lease_duration=timedelta(minutes=5),
                batch_size=10,
                max_attempts=3,
            )
            assert first.retryable == 1
            second = await run_worker_once(
                factory,
                gateway=gateway,
                worker_id="worker-b",
                now=now + timedelta(seconds=30),
                lease_duration=timedelta(minutes=5),
                batch_size=10,
                max_attempts=3,
            )
            assert second.sent == 1
            async with factory() as database:
                delivery = await database.scalar(
                    select(NotificationDelivery).where(
                        NotificationDelivery.reminder_id == reminder_id
                    )
                )
                assert delivery is not None
                return delivery
        finally:
            await engine.dispose()

    delivery = asyncio.run(exercise())

    assert delivery.status == "sent"
    assert delivery.attempt_count == 2
    assert delivery.last_error_code is None
    assert gateway.calls == ["niki-active", "niki-active"]
    assert gateway.confirmed_successes == ["niki-active"]


def test_transient_delivery_becomes_terminal_at_max_attempts(
    isolated_database_url: str,
) -> None:
    now = datetime.now(UTC)
    gateway = ScriptedGateway(
        {
            "niki-active": [
                PushResult(PushOutcome.TRANSIENT, "http_503"),
                PushResult(PushOutcome.TRANSIENT, "network_error"),
            ]
        }
    )

    async def exercise() -> NotificationDelivery:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            reminder_id, _ = await seed_due_reminder(
                factory,
                now=now,
                usernames=["niki"],
                subscription_expiries={"niki-active": None},
            )
            first = await run_worker_once(
                factory,
                gateway=gateway,
                worker_id="worker-a",
                now=now,
                lease_duration=timedelta(minutes=5),
                batch_size=10,
                max_attempts=2,
            )
            assert first.retryable == 1
            second = await run_worker_once(
                factory,
                gateway=gateway,
                worker_id="worker-b",
                now=now + timedelta(seconds=30),
                lease_duration=timedelta(minutes=5),
                batch_size=10,
                max_attempts=2,
            )
            assert second.failed == 1
            terminal = await run_worker_once(
                factory,
                gateway=gateway,
                worker_id="worker-c",
                now=now + timedelta(hours=1),
                lease_duration=timedelta(minutes=5),
                batch_size=10,
                max_attempts=2,
            )
            assert terminal.claimed == 0
            async with factory() as database:
                delivery = await database.scalar(
                    select(NotificationDelivery).where(
                        NotificationDelivery.reminder_id == reminder_id
                    )
                )
                assert delivery is not None
                return delivery
        finally:
            await engine.dispose()

    delivery = asyncio.run(exercise())

    assert delivery.status == "failed"
    assert delivery.attempt_count == 2
    assert delivery.next_attempt_at is None
    assert delivery.sent_at is None
    assert delivery.last_error_code == "network_error"
    assert gateway.calls == ["niki-active", "niki-active"]
