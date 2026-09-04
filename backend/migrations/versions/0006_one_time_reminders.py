"""Add one-time reminders.

Revision ID: 0006_one_time_reminders
Revises: 0005_list_items
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_one_time_reminders"
down_revision: str | Sequence[str] | None = "0005_list_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("creator_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("due_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_timezone", sa.String(length=100), nullable=False),
        sa.Column("is_urgent", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'cancelled')",
            name=op.f("ck_reminders_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["creator_user_id"],
            ["users.id"],
            name=op.f("fk_reminders_creator_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminders")),
    )
    op.create_index(
        op.f("ix_reminders_creator_user_id"),
        "reminders",
        ["creator_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_reminders_due_at_utc"), "reminders", ["due_at_utc"], unique=False)
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
