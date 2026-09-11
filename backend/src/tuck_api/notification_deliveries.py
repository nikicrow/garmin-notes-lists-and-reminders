from datetime import datetime, timedelta
from enum import StrEnum
from typing import cast

from sqlalchemy import func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from tuck_api.models import NotificationDelivery, Reminder, ReminderRecipient


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    SENT = "sent"
    RETRYABLE = "retryable"
    FAILED = "failed"


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
