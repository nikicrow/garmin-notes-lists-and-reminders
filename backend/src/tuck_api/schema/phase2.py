"""Immutable Phase 2 notification schema snapshot.

This snapshot copies the Phase 1 tables before adding notification persistence so
revision 0007 remains independent from future application schema changes.
"""

from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.schema import Table

from tuck_api.schema import phase1

metadata = MetaData(naming_convention=phase1.metadata.naming_convention)
for phase1_table in phase1.application_tables:
    phase1_table.to_metadata(metadata)

users = metadata.tables["users"]
user_sessions = metadata.tables["user_sessions"]
notes = metadata.tables["notes"]
lists = metadata.tables["lists"]
resource_memberships = metadata.tables["resource_memberships"]
list_items = metadata.tables["list_items"]
reminders = metadata.tables["reminders"]

push_subscriptions = Table(
    "push_subscriptions",
    metadata,
    Column("user_id", Uuid(as_uuid=True), nullable=False),
    Column("endpoint", Text, nullable=False),
    Column("p256dh", String(255), nullable=False),
    Column("auth", String(255), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("disabled_at", DateTime(timezone=True), nullable=True),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    PrimaryKeyConstraint("id", name="pk_push_subscriptions"),
    UniqueConstraint("endpoint"),
    Index("ix_push_subscriptions_user_id", "user_id"),
)

reminder_recipients = Table(
    "reminder_recipients",
    metadata,
    Column("reminder_id", Uuid(as_uuid=True), nullable=False),
    Column("user_id", Uuid(as_uuid=True), nullable=False),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    ForeignKeyConstraint(["reminder_id"], ["reminders.id"], ondelete="CASCADE"),
    ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    UniqueConstraint("reminder_id", "user_id"),
    PrimaryKeyConstraint("id", name="pk_reminder_recipients"),
    Index("ix_reminder_recipients_reminder_id", "reminder_id"),
    Index("ix_reminder_recipients_user_id", "user_id"),
)

notification_deliveries = Table(
    "notification_deliveries",
    metadata,
    Column("reminder_id", Uuid(as_uuid=True), nullable=False),
    Column("recipient_user_id", Uuid(as_uuid=True), nullable=False),
    Column("status", String(20), nullable=False, default="pending", server_default="pending"),
    Column("attempt_count", Integer, nullable=False, default=0, server_default=text("0")),
    Column("next_attempt_at", DateTime(timezone=True), nullable=True),
    Column("claimed_at", DateTime(timezone=True), nullable=True),
    Column("sent_at", DateTime(timezone=True), nullable=True),
    Column("last_error_code", String(100), nullable=True),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
    CheckConstraint(
        "status IN ('pending', 'processing', 'retrying', 'sent', 'failed')",
        name="status_valid",
    ),
    ForeignKeyConstraint(
        ["reminder_id", "recipient_user_id"],
        ["reminder_recipients.reminder_id", "reminder_recipients.user_id"],
        ondelete="CASCADE",
    ),
    UniqueConstraint("reminder_id", "recipient_user_id"),
    PrimaryKeyConstraint("id", name="pk_notification_deliveries"),
    Index("ix_notification_deliveries_status_next_attempt_at", "status", "next_attempt_at"),
)

application_tables = (
    users,
    user_sessions,
    notes,
    lists,
    resource_memberships,
    list_items,
    reminders,
    push_subscriptions,
    reminder_recipients,
    notification_deliveries,
)
