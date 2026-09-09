"""Add private and shared lists.

Revision ID: 0004_private_shared_lists
Revises: 0003_private_notes
Create Date: 2026-09-04

"""

from collections.abc import Sequence

from alembic import op

from tuck_api.schema.phase1 import lists, resource_memberships

revision: str = "0004_private_shared_lists"
down_revision: str | Sequence[str] | None = "0003_private_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        lists.name,
        *lists.columns,
        *lists.constraints,
    )
    op.create_index(op.f("ix_lists_owner_user_id"), lists.name, ["owner_user_id"], unique=False)

    op.create_table(
        resource_memberships.name,
        *resource_memberships.columns,
        *resource_memberships.constraints,
    )
    op.create_index(
        op.f("ix_resource_memberships_list_id"),
        resource_memberships.name,
        ["list_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_resource_memberships_user_id"),
        resource_memberships.name,
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_resource_memberships_user_id"), table_name="resource_memberships")
    op.drop_index(op.f("ix_resource_memberships_list_id"), table_name="resource_memberships")
    op.drop_table("resource_memberships")
    op.drop_index(op.f("ix_lists_owner_user_id"), table_name="lists")
    op.drop_table("lists")
