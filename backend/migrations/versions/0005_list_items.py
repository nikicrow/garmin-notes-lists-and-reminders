"""Add ordered list items.

Revision ID: 0005_list_items
Revises: 0004_private_shared_lists
Create Date: 2026-09-04

"""

from collections.abc import Sequence

from alembic import op

from tuck_api.schema.phase1 import list_items

revision: str = "0005_list_items"
down_revision: str | Sequence[str] | None = "0004_private_shared_lists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        list_items.name,
        *list_items.columns,
        *list_items.constraints,
    )
    for index in list_items.indexes:
        op.create_index(
            op.f(index.name),
            list_items.name,
            [c.name for c in index.columns],
            unique=index.unique,
        )

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
