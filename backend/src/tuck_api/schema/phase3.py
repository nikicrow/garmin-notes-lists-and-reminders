"""Immutable Phase 3 command-workflow schema snapshot."""

from uuid import uuid4

from sqlalchemy import (
    JSON,
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

from tuck_api.schema import phase2

metadata = MetaData(naming_convention=phase2.metadata.naming_convention)
for phase2_table in phase2.application_tables:
    phase2_table.to_metadata(metadata)

users = metadata.tables["users"]
user_sessions = metadata.tables["user_sessions"]
notes = metadata.tables["notes"]
lists = metadata.tables["lists"]
resource_memberships = metadata.tables["resource_memberships"]
list_items = metadata.tables["list_items"]
reminders = metadata.tables["reminders"]
push_subscriptions = metadata.tables["push_subscriptions"]
reminder_recipients = metadata.tables["reminder_recipients"]
notification_deliveries = metadata.tables["notification_deliveries"]
notification_deliveries.append_column(Column("claimed_by", String(100), nullable=True))
for constraint in tuple(notification_deliveries.constraints):
    if constraint.name == "ck_notification_deliveries_status_valid":
        notification_deliveries.constraints.remove(constraint)
notification_deliveries.append_constraint(
    CheckConstraint(
        "status IN ('pending', 'claimed', 'sent', 'retryable', 'failed')",
        name="status_valid",
    )
)

captures = Table(
    "captures",
    metadata,
    Column("user_id", Uuid(as_uuid=True), nullable=False),
    Column("source", String(30), nullable=False),
    Column("source_request_id", String(255), nullable=False),
    Column("raw_text", Text, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("reference_timezone", String(100), nullable=False),
    Column("status", String(30), nullable=False, default="received", server_default="received"),
    Column("active_execution_id", Uuid(as_uuid=True), nullable=True),
    Column("resulting_resource_summary", JSON, nullable=True),
    Column("safe_error_code", String(100), nullable=True),
    Column("receipt", Text, nullable=True),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    CheckConstraint(
        "source IN ('pwa_text', 'gemini_mcp', 'web_share', 'future_adapter')",
        name="source_valid",
    ),
    CheckConstraint(
        "status IN ('received', 'interpreting', 'needs_review', 'executing', "
        "'completed', 'failed')",
        name="status_valid",
    ),
    ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    PrimaryKeyConstraint("id", name="pk_captures"),
    UniqueConstraint("source", "user_id", "source_request_id"),
    Index("ix_captures_user_id_status_created_at", "user_id", "status", "created_at"),
)

agent_executions = Table(
    "agent_executions",
    metadata,
    Column("capture_id", Uuid(as_uuid=True), nullable=False),
    Column("attempt_number", Integer, nullable=False),
    Column("graph_version", String(30), nullable=False),
    Column("command_schema_version", String(30), nullable=False),
    Column("prompt_version", String(30), nullable=False),
    Column("model_provider", String(100), nullable=False),
    Column("model_name", String(100), nullable=False),
    Column("status", String(30), nullable=False),
    Column("structured_plan_json", JSON, nullable=True),
    Column("validation_issues_json", JSON, nullable=False),
    Column("policy_decision_json", JSON, nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Column("latency_ms", Integer, nullable=True),
    Column("safe_error_code", String(100), nullable=True),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    ForeignKeyConstraint(["capture_id"], ["captures.id"], ondelete="CASCADE"),
    PrimaryKeyConstraint("id", name="pk_agent_executions"),
    UniqueConstraint("capture_id", "attempt_number"),
    Index("ix_agent_executions_capture_id", "capture_id"),
)

agent_action_executions = Table(
    "agent_action_executions",
    metadata,
    Column("agent_execution_id", Uuid(as_uuid=True), nullable=False),
    Column("action_index", Integer, nullable=False),
    Column("action_type", String(50), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("validated_command_json", JSON, nullable=False),
    Column("status", String(30), nullable=False),
    Column("result_entity_type", String(50), nullable=True),
    Column("result_entity_id", Uuid(as_uuid=True), nullable=True),
    Column("result_summary_json", JSON, nullable=True),
    Column("id", Uuid(as_uuid=True), nullable=False, default=uuid4),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    ForeignKeyConstraint(["agent_execution_id"], ["agent_executions.id"], ondelete="CASCADE"),
    PrimaryKeyConstraint("id", name="pk_agent_action_executions"),
    UniqueConstraint("idempotency_key"),
    UniqueConstraint("agent_execution_id", "action_index"),
    Index("ix_agent_action_executions_agent_execution_id", "agent_execution_id"),
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
    captures,
    agent_executions,
    agent_action_executions,
)
