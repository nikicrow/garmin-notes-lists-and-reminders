"""Add private and shared lists.

Revision ID: 0004_private_shared_lists
Revises: 0003_private_notes
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_private_shared_lists"
down_revision: str | Sequence[str] | None = "0003_private_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lists",
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_lists_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lists")),
    )
    op.create_index(op.f("ix_lists_owner_user_id"), "lists", ["owner_user_id"], unique=False)
    op.create_table(
        "resource_memberships",
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["lists.id"],
            name=op.f("fk_resource_memberships_list_id_lists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_resource_memberships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resource_memberships")),
        sa.UniqueConstraint("list_id", "user_id", name=op.f("uq_resource_memberships_list_id")),
    )
    op.create_index(
        op.f("ix_resource_memberships_list_id"), "resource_memberships", ["list_id"], unique=False
    )
    op.create_index(
        op.f("ix_resource_memberships_user_id"), "resource_memberships", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_resource_memberships_user_id"), table_name="resource_memberships")
    op.drop_index(op.f("ix_resource_memberships_list_id"), table_name="resource_memberships")
    op.drop_table("resource_memberships")
    op.drop_index(op.f("ix_lists_owner_user_id"), table_name="lists")
    op.drop_table("lists")
