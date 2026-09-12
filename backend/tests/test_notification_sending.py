import asyncio
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from tuck_api.db import create_engine, create_session_factory, session_scope
from tuck_api.models import (
    Base,
    NotificationDelivery,
    PushSubscription,
    Reminder,
    ReminderRecipient,
    User,
)
from tuck_api.notification_deliveries import PushGateway, send_claimed_delivery
from tuck_api.reminders import transition_reminder
from tuck_api.security import hash_password
from tuck_api.web_push import NotificationPayload, PushOutcome, PushResult, PushSubscriptionData


class RecordingGateway:
    def __init__(self, results: Sequence[PushResult]) -> None:
        self.results = iter(results)
        self.calls: list[tuple[PushSubscriptionData, NotificationPayload]] = []

    def send(self, subscription: PushSubscriptionData, payload: NotificationPayload) -> PushResult:
        self.calls.append((subscription, payload))
        return next(self.results)


class TimingOutGateway:
    def send(self, subscription: PushSubscriptionData, payload: NotificationPayload) -> PushResult:
        raise TimeoutError("provider response timed out")


class PausingGateway:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()

    def send(self, subscription: PushSubscriptionData, payload: NotificationPayload) -> PushResult:
        self.entered.set()
        assert self.release.wait(timeout=5)
        return PushResult.success()


async def seed_and_send(
    isolated_database_url: str,
    *,
    gateway: PushGateway,
    now: datetime,
    attempt_count: int = 1,
    max_attempts: int = 5,
    subscription_count: int = 1,
    reminder_status: str = "pending",
) -> tuple[NotificationDelivery, list[PushSubscription]]:
    engine = create_engine(isolated_database_url)
    factory = create_session_factory(engine)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_scope(factory) as database:
            user = User(id=uuid4(), username="niki", password_hash=hash_password("password"))
            database.add(user)
            await database.flush()
            reminder = Reminder(
                creator_user_id=user.id,
                title="Private reminder title",
                detail="Private reminder detail",
                due_at_utc=now,
                source_timezone="Australia/Brisbane",
                is_urgent=True,
                status=reminder_status,
            )
            reminder.recipient_links = [ReminderRecipient(user_id=user.id)]
            database.add(reminder)
            database.add_all(
                [
                    PushSubscription(
                        user_id=user.id,
                        endpoint=f"https://push.example.test/subscription-{index}",
                        p256dh="public-key",
                        auth="auth-secret",
                    )
                    for index in range(subscription_count)
                ]
            )
            await database.flush()
            delivery = NotificationDelivery(
                reminder_id=reminder.id,
                recipient_user_id=user.id,
                status="claimed",
                attempt_count=attempt_count,
                next_attempt_at=now,
                claimed_at=now,
                claimed_by="worker-1",
            )
            database.add(delivery)
            await database.flush()
            delivery_id: UUID = delivery.id

        async with session_scope(factory) as database:
            claimed_delivery = await database.get(NotificationDelivery, delivery_id)
            assert claimed_delivery is not None
            await send_claimed_delivery(
                database,
                claimed_delivery,
                gateway=gateway,
                now=now,
                max_attempts=max_attempts,
            )

        async with factory() as database:
            persisted = await database.scalar(
                select(NotificationDelivery).where(NotificationDelivery.id == delivery_id)
            )
            subscriptions = list(await database.scalars(select(PushSubscription)))
            assert persisted is not None
            return persisted, subscriptions
    finally:
        await engine.dispose()


def test_successful_send_persists_delivery_history(isolated_database_url: str) -> None:
    now = datetime.now(UTC)
    gateway = RecordingGateway([PushResult.success()])

    persisted, _ = asyncio.run(seed_and_send(isolated_database_url, gateway=gateway, now=now))

    assert persisted.status == "sent"
    assert persisted.sent_at == now
    assert persisted.last_error_code is None
    assert persisted.claimed_at is None
    assert persisted.claimed_by is None
    assert len(gateway.calls) == 1
    subscription, payload = gateway.calls[0]
    assert subscription["endpoint"] == "https://push.example.test/subscription-0"
    assert payload["data"]["urgency"] == "high"
    assert "Private reminder" not in str(payload)


@pytest.mark.parametrize("reminder_status", ["completed", "cancelled"])
def test_terminal_reminder_is_not_delivered(
    isolated_database_url: str, reminder_status: str
) -> None:
    now = datetime.now(UTC)
    gateway = RecordingGateway([PushResult.success()])

    persisted, _ = asyncio.run(
        seed_and_send(
            isolated_database_url,
            gateway=gateway,
            now=now,
            reminder_status=reminder_status,
        )
    )

    assert gateway.calls == []
    assert persisted.status == "failed"
    assert persisted.last_error_code == "reminder_not_pending"
    assert persisted.next_attempt_at is None


def test_delivery_serializes_with_terminal_reminder_transition(
    isolated_database_url: str,
) -> None:
    now = datetime.now(UTC)
    gateway = PausingGateway()

    async def seed() -> tuple[UUID, UUID, UUID]:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with session_scope(factory) as database:
                owner = User(username="niki", password_hash=hash_password("password"))
                database.add(owner)
                await database.flush()
                reminder = Reminder(
                    creator_user_id=owner.id,
                    title="Private reminder",
                    detail=None,
                    due_at_utc=now,
                    source_timezone="UTC",
                    is_urgent=False,
                )
                reminder.recipient_links = [ReminderRecipient(user_id=owner.id)]
                database.add(reminder)
                database.add(
                    PushSubscription(
                        user_id=owner.id,
                        endpoint="https://push.example.test/subscription",
                        p256dh="public-key",
                        auth="auth-secret",
                    )
                )
                await database.flush()
                delivery = NotificationDelivery(
                    reminder_id=reminder.id,
                    recipient_user_id=owner.id,
                    status="claimed",
                    attempt_count=1,
                    next_attempt_at=now,
                    claimed_at=now,
                    claimed_by="worker-1",
                )
                database.add(delivery)
                await database.flush()
                return owner.id, reminder.id, delivery.id
        finally:
            await engine.dispose()

    owner_id, reminder_id, delivery_id = asyncio.run(seed())

    async def send() -> None:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as database:
                delivery = await database.get(NotificationDelivery, delivery_id)
                assert delivery is not None
                await send_claimed_delivery(
                    database,
                    delivery,
                    gateway=gateway,
                    now=now,
                    max_attempts=5,
                )
        finally:
            await engine.dispose()

    async def cancel() -> None:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as database:
                owner = await database.get(User, owner_id)
                assert owner is not None
                await transition_reminder(database, owner, reminder_id, "cancelled")
        finally:
            await engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        send_future = executor.submit(asyncio.run, send())
        assert gateway.entered.wait(timeout=5)
        cancel_future = executor.submit(asyncio.run, cancel())
        try:
            with pytest.raises(FutureTimeoutError):
                cancel_future.result(timeout=0.2)
        finally:
            gateway.release.set()
        send_future.result(timeout=5)
        cancel_future.result(timeout=5)

    async def persisted_states() -> tuple[str, str]:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with factory() as database:
                reminder = await database.get(Reminder, reminder_id)
                delivery = await database.get(NotificationDelivery, delivery_id)
                assert reminder is not None and delivery is not None
                return reminder.status, delivery.status
        finally:
            await engine.dispose()

    assert asyncio.run(persisted_states()) == ("cancelled", "sent")


def test_expired_subscription_is_disabled_and_delivery_fails(
    isolated_database_url: str,
) -> None:
    now = datetime.now(UTC)
    gateway = RecordingGateway([PushResult(PushOutcome.EXPIRED, "http_410")])

    persisted, subscriptions = asyncio.run(
        seed_and_send(isolated_database_url, gateway=gateway, now=now)
    )

    assert persisted.status == "failed"
    assert persisted.last_error_code == "http_410"
    assert persisted.sent_at is None
    assert persisted.next_attempt_at is None
    assert subscriptions[0].disabled_at == now


def test_transient_failure_uses_bounded_exponential_backoff(
    isolated_database_url: str,
) -> None:
    now = datetime.now(UTC)
    gateway = RecordingGateway([PushResult(PushOutcome.TRANSIENT, "http_503")])

    persisted, subscriptions = asyncio.run(
        seed_and_send(
            isolated_database_url,
            gateway=gateway,
            now=now,
            attempt_count=3,
        )
    )

    assert persisted.status == "retryable"
    assert persisted.next_attempt_at == now.replace(microsecond=now.microsecond) + timedelta(
        minutes=2
    )
    assert persisted.last_error_code == "http_503"
    assert persisted.claimed_at is None
    assert persisted.claimed_by is None
    assert subscriptions[0].disabled_at is None


def test_transient_failure_at_maximum_attempts_becomes_terminal(
    isolated_database_url: str,
) -> None:
    now = datetime.now(UTC)
    gateway = RecordingGateway([PushResult(PushOutcome.TRANSIENT, "network_error")])

    persisted, _ = asyncio.run(
        seed_and_send(
            isolated_database_url,
            gateway=gateway,
            now=now,
            attempt_count=5,
            max_attempts=5,
        )
    )

    assert persisted.status == "failed"
    assert persisted.next_attempt_at is None
    assert persisted.last_error_code == "network_error"


def test_unexpected_provider_timeout_is_recorded_for_retry(
    isolated_database_url: str,
) -> None:
    now = datetime.now(UTC)

    persisted, _ = asyncio.run(
        seed_and_send(
            isolated_database_url,
            gateway=TimingOutGateway(),
            now=now,
        )
    )

    assert persisted.status == "retryable"
    assert persisted.next_attempt_at == now + timedelta(seconds=30)
    assert persisted.last_error_code == "network_error"


def test_terminal_provider_failure_is_not_retried(isolated_database_url: str) -> None:
    now = datetime.now(UTC)
    gateway = RecordingGateway([PushResult(PushOutcome.TERMINAL, "http_400")])

    persisted, subscriptions = asyncio.run(
        seed_and_send(isolated_database_url, gateway=gateway, now=now)
    )

    assert persisted.status == "failed"
    assert persisted.next_attempt_at is None
    assert persisted.last_error_code == "http_400"
    assert subscriptions[0].disabled_at is None


def test_exponential_backoff_is_capped_at_one_hour(isolated_database_url: str) -> None:
    now = datetime.now(UTC)
    gateway = RecordingGateway([PushResult(PushOutcome.TRANSIENT, "http_429")])

    persisted, _ = asyncio.run(
        seed_and_send(
            isolated_database_url,
            gateway=gateway,
            now=now,
            attempt_count=9,
            max_attempts=10,
        )
    )

    assert persisted.status == "retryable"
    assert persisted.next_attempt_at == now + timedelta(hours=1)


def test_one_success_prevents_retrying_a_recipient_on_another_subscription(
    isolated_database_url: str,
) -> None:
    now = datetime.now(UTC)
    gateway = RecordingGateway(
        [PushResult.success(), PushResult(PushOutcome.TRANSIENT, "http_503")]
    )

    persisted, _ = asyncio.run(
        seed_and_send(
            isolated_database_url,
            gateway=gateway,
            now=now,
            subscription_count=2,
        )
    )

    assert persisted.status == "sent"
    assert persisted.next_attempt_at is None
    assert persisted.last_error_code is None
