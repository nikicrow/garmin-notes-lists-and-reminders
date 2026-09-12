import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

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


async def seed_and_send(
    isolated_database_url: str,
    *,
    gateway: PushGateway,
    now: datetime,
    attempt_count: int = 1,
    max_attempts: int = 5,
    subscription_count: int = 1,
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
