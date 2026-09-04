"""Add ordered list items.

Revision ID: 0005_list_items
Revises: 0004_private_shared_lists
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_list_items"
down_revision: str | Sequence[str] | None = "0004_private_shared_lists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "list_items",
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("position >= 0", name=op.f("ck_list_items_position_nonnegative")),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_list_items_created_by_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["lists.id"],
            name=op.f("fk_list_items_list_id_lists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_user_id"],
            ["users.id"],
            name=op.f("fk_list_items_completed_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_list_items")),
        sa.UniqueConstraint(
            "list_id",
            "position",
            name=op.f("uq_list_items_list_id"),
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(
        op.f("ix_list_items_created_by_user_id"),
        "list_items",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_list_items_completed_by_user_id"),
        "list_items",
        ["completed_by_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_list_items_list_id"), "list_items", ["list_id"], unique=False)

    # Trigger function and trigger for updated_at auto-update
    op.execute(
        """
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = now();
        RETURN NEW;
    END;
    $$ language 'plpgsql';
    """
    )
    op.execute(
        """
    CREATE TRIGGER update_list_items_updated_at
    BEFORE UPDATE ON list_items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
    """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_list_items_list_id"), table_name="list_items")
    op.execute("DROP TRIGGER IF EXISTS update_list_items_updated_at ON list_items")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    op.drop_index(op.f("ix_list_items_completed_by_user_id"), table_name="list_items")
    op.drop_index(op.f("ix_list_items_created_by_user_id"), table_name="list_items")
    op.drop_table("list_items")
