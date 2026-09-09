"""Add owned private notes.

Revision ID: 0003_private_notes
Revises: 0002_user_accounts
Create Date: 2026-09-04

"""

from collections.abc import Sequence

from alembic import op

from tuck_api.schema.phase1 import notes

revision: str = "0003_private_notes"
down_revision: str | Sequence[str] | None = "0002_user_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        notes.name,
        *notes.columns,
        *notes.constraints,
    )
    op.create_index(op.f("ix_notes_owner_user_id"), notes.name, ["owner_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notes_owner_user_id"), table_name="notes")
    op.drop_table("notes")
