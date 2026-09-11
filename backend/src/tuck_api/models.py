from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tuck_api import schema


class Base(DeclarativeBase):
    """Declarative base backed by Tuck's canonical SQLAlchemy schema."""

    metadata = schema.metadata


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    __table__ = schema.users

    username: Mapped[str]
    password_hash: Mapped[str]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class UserSession(Base):
    __table__ = schema.user_sessions

    user_id: Mapped[UUID]
    token_hash: Mapped[str]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class Note(Base):
    __table__ = schema.notes

    owner_user_id: Mapped[UUID]
    body: Mapped[str]
    archived_at: Mapped[datetime | None]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class List(Base):
    __table__ = schema.lists

    owner_user_id: Mapped[UUID]
    title: Mapped[str]
    archived_at: Mapped[datetime | None]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class ResourceMembership(Base):
    __table__ = schema.resource_memberships

    list_id: Mapped[UUID]
    user_id: Mapped[UUID]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class ListItem(Base):
    __table__ = schema.list_items

    list_id: Mapped[UUID]
    body: Mapped[str]
    position: Mapped[int]
    created_by_user_id: Mapped[UUID]
    completed_at: Mapped[datetime | None]
    completed_by_user_id: Mapped[UUID | None]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class Reminder(Base):
    __table__ = schema.reminders

    creator_user_id: Mapped[UUID]
    title: Mapped[str]
    detail: Mapped[str | None]
    due_at_utc: Mapped[datetime]
    source_timezone: Mapped[str]
    is_urgent: Mapped[bool]
    status: Mapped[str]
    completed_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class PushSubscription(Base):
    __table__ = schema.push_subscriptions

    user_id: Mapped[UUID]
    endpoint: Mapped[str]
    p256dh: Mapped[str]
    auth: Mapped[str]
    expires_at: Mapped[datetime | None]
    disabled_at: Mapped[datetime | None]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class ReminderRecipient(Base):
    __table__ = schema.reminder_recipients

    reminder_id: Mapped[UUID]
    user_id: Mapped[UUID]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class NotificationDelivery(Base):
    __table__ = schema.notification_deliveries

    reminder_id: Mapped[UUID]
    recipient_user_id: Mapped[UUID]
    status: Mapped[str]
    attempt_count: Mapped[int]
    next_attempt_at: Mapped[datetime | None]
    claimed_at: Mapped[datetime | None]
    sent_at: Mapped[datetime | None]
    last_error_code: Mapped[str | None]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
