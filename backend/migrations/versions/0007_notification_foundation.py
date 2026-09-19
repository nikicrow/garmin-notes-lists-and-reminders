"""Add notification persistence foundation.

Revision ID: 0007_notification_foundation
Revises: 0006_one_time_reminders
Create Date: 2026-09-11

"""

from collections.abc import Sequence

from alembic import op

from tuck_api.schema.phase2 import (
    notification_deliveries,
    push_subscriptions,
    reminder_recipients,
)

revision: str = "0007_notification_foundation"
down_revision: str | Sequence[str] | None = "0006_one_time_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_table(table_name: str) -> None:
    table = {
        push_subscriptions.name: push_subscriptions,
        reminder_recipients.name: reminder_recipients,
        notification_deliveries.name: notification_deliveries,
    }[table_name]
    op.create_table(table.name, *table.columns, *table.constraints)


def _create_updated_at_trigger(table_name: str) -> None:
    op.execute(
        f"""
        CREATE TRIGGER update_{table_name}_updated_at
        BEFORE UPDATE ON {table_name}
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
        """
    )


def upgrade() -> None:
    _create_table(push_subscriptions.name)
    op.create_index(
        op.f("ix_push_subscriptions_user_id"),
        push_subscriptions.name,
        ["user_id"],
        unique=False,
    )
    _create_updated_at_trigger(push_subscriptions.name)

    _create_table(reminder_recipients.name)
    op.create_index(
        op.f("ix_reminder_recipients_reminder_id"),
        reminder_recipients.name,
        ["reminder_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reminder_recipients_user_id"),
        reminder_recipients.name,
        ["user_id"],
        unique=False,
    )
    _create_updated_at_trigger(reminder_recipients.name)

    _create_table(notification_deliveries.name)
    op.create_index(
        op.f("ix_notification_deliveries_status_next_attempt_at"),
        notification_deliveries.name,
        ["status", "next_attempt_at"],
        unique=False,
    )
    _create_updated_at_trigger(notification_deliveries.name)


def downgrade() -> None:
    for table_name in (
        notification_deliveries.name,
        reminder_recipients.name,
        push_subscriptions.name,
    ):
        op.execute(f"DROP TRIGGER IF EXISTS update_{table_name}_updated_at ON {table_name}")

    op.drop_index(
        op.f("ix_notification_deliveries_status_next_attempt_at"),
        table_name=notification_deliveries.name,
    )
    op.drop_table(notification_deliveries.name)
    op.drop_index(op.f("ix_reminder_recipients_user_id"), table_name=reminder_recipients.name)
    op.drop_index(op.f("ix_reminder_recipients_reminder_id"), table_name=reminder_recipients.name)
    op.drop_table(reminder_recipients.name)
    op.drop_index(op.f("ix_push_subscriptions_user_id"), table_name=push_subscriptions.name)
    op.drop_table(push_subscriptions.name)
