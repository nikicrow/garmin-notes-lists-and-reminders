"""Immutable Phase 1 schema snapshot used by Alembic revisions 0002–0006.

These ``Table`` objects are the single source of truth for column layouts,
constraints, and index definitions used by Alembic migration scripts and any
other tooling that inspects the database schema directly.

They are deliberately Core tables rather than ORM models, because:

* ORM models live in :mod:`tuck_api.models` and describe the object layer
  (relationships, mixins, attribute access) that the application code uses.
* Migration scripts describe the database schema as DDL. A shared Core table
  definition is the natural place to state that DDL once and reuse it across
  every migration that touches the same table.

Do not edit these table definitions after the Phase 1 migrations land. Later
schema changes belong in a new migration and in the current schema assembled by
``tuck_api.schema``. Keeping this module immutable prevents old migrations from
changing behavior on fresh installations.

Naming convention
----------------

The ``MetaData`` below carries the same naming convention the ORM uses, so
foreign keys, indexes, unique constraints, and check constraints get their
names generated automatically by SQLAlchemy. Only primary-key constraint names
are passed explicitly because they are short, stable, and read well in DDL
output.
"""

from uuid import uuid4

from sqlalchemy import (
    Boolean,
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
)
from sqlalchemy.schema import Table

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    },
)


# ---------------------------------------------------------------------------
# Users and sessions
# ---------------------------------------------------------------------------

users = Table(
    "users",
    metadata,
    Column("username", String(100), nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    PrimaryKeyConstraint("id", name="pk_users"),
    Index("ix_users_username", "username", unique=True),
)


user_sessions = Table(
    "user_sessions",
    metadata,
    Column("user_id", Uuid(as_uuid=True), nullable=False),
    Column("token_hash", String(64), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    ForeignKeyConstraint(
        ["user_id"],
        ["users.id"],
        ondelete="CASCADE",
    ),
    PrimaryKeyConstraint("id", name="pk_user_sessions"),
    Index("ix_user_sessions_user_id", "user_id"),
    Index("ix_user_sessions_token_hash", "token_hash", unique=True),
    Index("ix_user_sessions_expires_at", "expires_at"),
)


# ---------------------------------------------------------------------------
# Owned content
# ---------------------------------------------------------------------------

notes = Table(
    "notes",
    metadata,
    Column("owner_user_id", Uuid(as_uuid=True), nullable=False),
    Column("body", Text, nullable=False),
    Column("archived_at", DateTime(timezone=True), nullable=True),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    ForeignKeyConstraint(
        ["owner_user_id"],
        ["users.id"],
        ondelete="CASCADE",
    ),
    PrimaryKeyConstraint("id", name="pk_notes"),
    Index("ix_notes_owner_user_id", "owner_user_id"),
)


lists = Table(
    "lists",
    metadata,
    Column("owner_user_id", Uuid(as_uuid=True), nullable=False),
    Column("title", String(200), nullable=False),
    Column("archived_at", DateTime(timezone=True), nullable=True),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    ForeignKeyConstraint(
        ["owner_user_id"],
        ["users.id"],
        ondelete="CASCADE",
    ),
    PrimaryKeyConstraint("id", name="pk_lists"),
    Index("ix_lists_owner_user_id", "owner_user_id"),
)


# ---------------------------------------------------------------------------
# Sharing
# ---------------------------------------------------------------------------

resource_memberships = Table(
    "resource_memberships",
    metadata,
    Column("list_id", Uuid(as_uuid=True), nullable=False),
    Column("user_id", Uuid(as_uuid=True), nullable=False),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    ForeignKeyConstraint(
        ["list_id"],
        ["lists.id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["user_id"],
        ["users.id"],
        ondelete="CASCADE",
    ),
    UniqueConstraint("list_id", "user_id"),
    PrimaryKeyConstraint("id", name="pk_resource_memberships"),
    Index("ix_resource_memberships_list_id", "list_id"),
    Index("ix_resource_memberships_user_id", "user_id"),
)


# ---------------------------------------------------------------------------
# List items
# ---------------------------------------------------------------------------

list_items = Table(
    "list_items",
    metadata,
    Column("list_id", Uuid(as_uuid=True), nullable=False),
    Column("body", Text, nullable=False),
    Column("position", Integer, nullable=False),
    Column("created_by_user_id", Uuid(as_uuid=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Column("completed_by_user_id", Uuid(as_uuid=True), nullable=True),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    CheckConstraint("position >= 0", name="position_nonnegative"),
    ForeignKeyConstraint(
        ["list_id"],
        ["lists.id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["created_by_user_id"],
        ["users.id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["completed_by_user_id"],
        ["users.id"],
        ondelete="SET NULL",
    ),
    UniqueConstraint("list_id", "position", deferrable=True, initially="DEFERRED"),
    PrimaryKeyConstraint("id", name="pk_list_items"),
    Index("ix_list_items_list_id", "list_id"),
    Index("ix_list_items_created_by_user_id", "created_by_user_id"),
    Index("ix_list_items_completed_by_user_id", "completed_by_user_id"),
)


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

reminders = Table(
    "reminders",
    metadata,
    Column("creator_user_id", Uuid(as_uuid=True), nullable=False),
    Column("title", String(200), nullable=False),
    Column("detail", Text, nullable=True),
    Column("due_at_utc", DateTime(timezone=True), nullable=False),
    Column("source_timezone", String(100), nullable=False),
    Column("is_urgent", Boolean, nullable=False, default=False),
    Column("status", String(20), nullable=False, default="pending"),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Column("cancelled_at", DateTime(timezone=True), nullable=True),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    CheckConstraint(
        "status IN ('pending', 'completed', 'cancelled')",
        name="status_valid",
    ),
    ForeignKeyConstraint(
        ["creator_user_id"],
        ["users.id"],
        ondelete="CASCADE",
    ),
    PrimaryKeyConstraint("id", name="pk_reminders"),
    Index("ix_reminders_creator_user_id", "creator_user_id"),
    Index("ix_reminders_due_at_utc", "due_at_utc"),
)


application_tables = (
    users,
    user_sessions,
    notes,
    lists,
    resource_memberships,
    list_items,
    reminders,
)
