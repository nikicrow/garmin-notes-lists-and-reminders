"""Establish the initial migration baseline.

Revision ID: 0001_initial_infrastructure
Revises:
Create Date: 2026-09-04

"""

from collections.abc import Sequence

revision: str = "0001_initial_infrastructure"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
