"""Add one-time reminders.

Revision ID: 0006_one_time_reminders
Revises: 0005_list_items
Create Date: 2026-09-04

"""

from collections.abc import Sequence

from alembic import op

from tuck_api.schema.phase1 import reminders

revision: str = "0006_one_time_reminders"
down_revision: str | Sequence[str] | None = "0005_list_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        reminders.name,
        *reminders.columns,
        *reminders.constraints,
    )
    op.create_index(
        op.f("ix_reminders_creator_user_id"),
        reminders.name,
        ["creator_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_reminders_due_at_utc"), reminders.name, ["due_at_utc"], unique=False)
    op.execute(
        """
        CREATE TRIGGER update_reminders_updated_at
        BEFORE UPDATE ON reminders
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS update_reminders_updated_at ON reminders")
    op.drop_index(op.f("ix_reminders_due_at_utc"), table_name="reminders")
    op.drop_index(op.f("ix_reminders_creator_user_id"), table_name="reminders")
    op.drop_table("reminders")
