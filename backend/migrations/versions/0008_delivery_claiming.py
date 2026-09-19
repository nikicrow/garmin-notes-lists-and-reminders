"""Add idempotent delivery claiming.

Revision ID: 0008_delivery_claiming
Revises: 0007_notification_foundation
Create Date: 2026-09-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_delivery_claiming"
down_revision: str | Sequence[str] | None = "0007_notification_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_STATUS_CONSTRAINT = "ck_notification_deliveries_status_valid"


def upgrade() -> None:
    op.add_column(
        "notification_deliveries",
        sa.Column("claimed_by", sa.String(length=100), nullable=True),
    )
    op.drop_constraint(op.f(_STATUS_CONSTRAINT), "notification_deliveries", type_="check")
    op.execute("UPDATE notification_deliveries SET status = 'claimed' WHERE status = 'processing'")
    op.execute("UPDATE notification_deliveries SET status = 'retryable' WHERE status = 'retrying'")
    op.create_check_constraint(
        op.f(_STATUS_CONSTRAINT),
        "notification_deliveries",
        "status IN ('pending', 'claimed', 'sent', 'retryable', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f(_STATUS_CONSTRAINT), "notification_deliveries", type_="check")
    op.execute("UPDATE notification_deliveries SET status = 'processing' WHERE status = 'claimed'")
    op.execute("UPDATE notification_deliveries SET status = 'retrying' WHERE status = 'retryable'")
    op.create_check_constraint(
        op.f(_STATUS_CONSTRAINT),
        "notification_deliveries",
        "status IN ('pending', 'processing', 'retrying', 'sent', 'failed')",
    )
    op.drop_column("notification_deliveries", "claimed_by")
