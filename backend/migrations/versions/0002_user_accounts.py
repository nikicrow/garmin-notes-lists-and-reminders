"""Add user accounts and server-side sessions.

Revision ID: 0002_user_accounts
Revises: 0001_initial_infrastructure
Create Date: 2026-09-04

"""

from collections.abc import Sequence

from alembic import op

from tuck_api.schema.phase1 import user_sessions, users

revision: str = "0002_user_accounts"
down_revision: str | Sequence[str] | None = "0001_initial_infrastructure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        users.name,
        *users.columns,
        *users.constraints,
    )
    op.create_index(op.f("ix_users_username"), users.name, ["username"], unique=True)

    op.create_table(
        user_sessions.name,
        *user_sessions.columns,
        *user_sessions.constraints,
    )
    op.create_index(
        op.f("ix_user_sessions_expires_at"),
        user_sessions.name,
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_sessions_token_hash"),
        user_sessions.name,
        ["token_hash"],
        unique=True,
    )
    op.create_index(op.f("ix_user_sessions_user_id"), user_sessions.name, ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_token_hash"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_expires_at"), table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
