from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, cast

from sqlalchemy import func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from tuck_api.models import (
    NotificationDelivery,
    PushSubscription,
    Reminder,
    ReminderRecipient,
)
from tuck_api.web_push import (
    NotificationPayload,
    PushOutcome,
    PushResult,
    PushSubscriptionData,
    build_notification_payload,
)


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    SENT = "sent"
    RETRYABLE = "retryable"
    FAILED = "failed"


class PushGateway(Protocol):
    def send(
        self, subscription: PushSubscriptionData, payload: NotificationPayload
    ) -> PushResult: ...


async def send_claimed_delivery(
    database: AsyncSession,
    delivery: NotificationDelivery,
    *,
    gateway: PushGateway,
    now: datetime,
    max_attempts: int,
) -> None:
    reminder = await database.scalar(
        select(Reminder).where(Reminder.id == delivery.reminder_id).with_for_update()
    )
    if reminder is None:
        raise ValueError("delivery reminder does not exist")
    if reminder.status != "pending":
        delivery.status = DeliveryStatus.FAILED
        delivery.sent_at = None
        delivery.next_attempt_at = None
        delivery.claimed_at = None
        delivery.claimed_by = None
        delivery.last_error_code = "reminder_not_pending"
        await database.flush()
        return
    subscriptions = list(
        await database.scalars(
            select(PushSubscription).where(
                PushSubscription.user_id == delivery.recipient_user_id,
                PushSubscription.disabled_at.is_(None),
                or_(PushSubscription.expires_at.is_(None), PushSubscription.expires_at > now),
            )
        )
    )
    payload = build_notification_payload(reminder_id=reminder.id, urgent=reminder.is_urgent)
    results: list[tuple[PushSubscription, PushResult]] = []
    for subscription in subscriptions:
        try:
            result = gateway.send(
                {
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                payload,
            )
        except TimeoutError:
            result = PushResult(PushOutcome.TRANSIENT, "network_error")
        results.append((subscription, result))
    for subscription, result in results:
        if result.outcome == PushOutcome.EXPIRED:
            subscription.disabled_at = now
    if results and all(result.outcome == PushOutcome.EXPIRED for _, result in results):
        delivery.status = DeliveryStatus.FAILED
        delivery.sent_at = None
        delivery.next_attempt_at = None
        delivery.claimed_at = None
        delivery.claimed_by = None
        delivery.last_error_code = results[-1][1].error_code
        await database.flush()
        return
    if any(result.outcome == PushOutcome.SUCCESS for _, result in results):
        delivery.status = DeliveryStatus.SENT
        delivery.sent_at = now
        delivery.next_attempt_at = None
        delivery.claimed_at = None
        delivery.claimed_by = None
        delivery.last_error_code = None
        await database.flush()
        return
    transient_results = [result for _, result in results if result.outcome == PushOutcome.TRANSIENT]
    if transient_results and delivery.attempt_count < max_attempts:
        backoff_seconds = min(30 * 2 ** (delivery.attempt_count - 1), 3600)
        delivery.status = DeliveryStatus.RETRYABLE
        delivery.sent_at = None
        delivery.next_attempt_at = now + timedelta(seconds=backoff_seconds)
        delivery.claimed_at = None
        delivery.claimed_by = None
        delivery.last_error_code = transient_results[-1].error_code
        await database.flush()
        return
    delivery.status = DeliveryStatus.FAILED
    delivery.sent_at = None
    delivery.next_attempt_at = None
    delivery.claimed_at = None
    delivery.claimed_by = None
    delivery.last_error_code = results[-1][1].error_code if results else "no_subscription"
    await database.flush()


async def materialize_due_deliveries(database: AsyncSession, *, now: datetime) -> int:
    """Create at most one delivery for each recipient of a due reminder."""

    due_recipients = (
        select(
            func.gen_random_uuid(),
            ReminderRecipient.reminder_id,
            ReminderRecipient.user_id,
            literal(DeliveryStatus.PENDING),
            literal(0),
            literal(now),
        )
        .join(Reminder, Reminder.id == ReminderRecipient.reminder_id)
        .where(Reminder.status == "pending", Reminder.due_at_utc <= now)
    )
    statement = (
        insert(NotificationDelivery)
        .from_select(
            [
                NotificationDelivery.id,
                NotificationDelivery.reminder_id,
                NotificationDelivery.recipient_user_id,
                NotificationDelivery.status,
                NotificationDelivery.attempt_count,
                NotificationDelivery.next_attempt_at,
            ],
            due_recipients,
        )
        .on_conflict_do_nothing(
            index_elements=[
                NotificationDelivery.reminder_id,
                NotificationDelivery.recipient_user_id,
            ]
        )
    )
    result = cast(CursorResult[tuple[object, ...]], await database.execute(statement))
    return result.rowcount


async def claim_due_deliveries(
    database: AsyncSession,
    *,
    worker_id: str,
    now: datetime,
    lease_duration: timedelta,
    limit: int,
) -> list[NotificationDelivery]:
    """Lock and claim available deliveries for one worker."""

    lease_expired_at = now - lease_duration
    available = or_(
        (
            NotificationDelivery.status.in_([DeliveryStatus.PENDING, DeliveryStatus.RETRYABLE])
            & (NotificationDelivery.next_attempt_at <= now)
        ),
        (
            (NotificationDelivery.status == DeliveryStatus.CLAIMED)
            & (NotificationDelivery.claimed_at <= lease_expired_at)
        ),
    )
    deliveries = list(
        await database.scalars(
            select(NotificationDelivery)
            .where(available)
            .order_by(NotificationDelivery.next_attempt_at, NotificationDelivery.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    for delivery in deliveries:
        delivery.status = DeliveryStatus.CLAIMED
        delivery.claimed_by = worker_id
        delivery.claimed_at = now
        delivery.attempt_count += 1
    await database.flush()
    return deliveries
