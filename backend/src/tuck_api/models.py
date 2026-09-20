from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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
    recipient_links: Mapped[list[ReminderRecipient]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ReminderRecipient.user_id",
    )
    deliveries: Mapped[list[NotificationDelivery]] = relationship(
        lazy="selectin",
        order_by="NotificationDelivery.recipient_user_id",
        primaryjoin="Reminder.id == foreign(NotificationDelivery.reminder_id)",
        viewonly=True,
    )
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    @property
    def recipient_user_ids(self) -> list[UUID]:
        return [recipient.user_id for recipient in self.recipient_links]


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
    claimed_by: Mapped[str | None]
    sent_at: Mapped[datetime | None]
    last_error_code: Mapped[str | None]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class Capture(Base):
    __table__ = schema.captures

    user_id: Mapped[UUID]
    source: Mapped[str]
    source_request_id: Mapped[str]
    raw_text: Mapped[str]
    occurred_at: Mapped[datetime]
    reference_timezone: Mapped[str]
    status: Mapped[str]
    active_execution_id: Mapped[UUID | None]
    resulting_resource_summary: Mapped[list[dict[str, Any]] | None]
    safe_error_code: Mapped[str | None]
    receipt: Mapped[str | None]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class AgentExecution(Base):
    __table__ = schema.agent_executions

    capture_id: Mapped[UUID]
    attempt_number: Mapped[int]
    graph_version: Mapped[str]
    command_schema_version: Mapped[str]
    prompt_version: Mapped[str]
    model_provider: Mapped[str]
    model_name: Mapped[str]
    status: Mapped[str]
    structured_plan_json: Mapped[dict[str, Any] | None]
    validation_issues_json: Mapped[list[dict[str, Any]]]
    policy_decision_json: Mapped[dict[str, Any] | None]
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
    latency_ms: Mapped[int | None]
    safe_error_code: Mapped[str | None]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class AgentActionExecution(Base):
    __table__ = schema.agent_action_executions

    agent_execution_id: Mapped[UUID]
    action_index: Mapped[int]
    action_type: Mapped[str]
    idempotency_key: Mapped[str]
    validated_command_json: Mapped[dict[str, Any]]
    status: Mapped[str]
    result_entity_type: Mapped[str | None]
    result_entity_id: Mapped[UUID | None]
    result_summary_json: Mapped[dict[str, Any] | None]
    id: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
