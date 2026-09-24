"""Add the durable command workflow.

Revision ID: 0009_command_workflow
Revises: 0008_delivery_claiming
Create Date: 2026-09-20

"""

from collections.abc import Sequence

from alembic import op

from tuck_api.schema.phase3 import agent_action_executions, agent_executions, captures

revision: str = "0009_command_workflow"
down_revision: str | Sequence[str] | None = "0008_delivery_claiming"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_table(table: object) -> None:
    op.create_table(table.name, *table.columns, *table.constraints)  # type: ignore[attr-defined]


def _create_updated_at_trigger(table_name: str) -> None:
    op.execute(
        f"""
        CREATE TRIGGER update_{table_name}_updated_at
        BEFORE UPDATE ON {table_name}
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
        """
    )


def upgrade() -> None:
    for table in (captures, agent_executions, agent_action_executions):
        _create_table(table)
        _create_updated_at_trigger(table.name)

    op.create_index(
        op.f("ix_captures_user_id_status_created_at"),
        captures.name,
        ["user_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_executions_capture_id"),
        agent_executions.name,
        ["capture_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_action_executions_agent_execution_id"),
        agent_action_executions.name,
        ["agent_execution_id"],
        unique=False,
    )


def downgrade() -> None:
    for table_name in (
        agent_action_executions.name,
        agent_executions.name,
        captures.name,
    ):
        op.execute(f"DROP TRIGGER IF EXISTS update_{table_name}_updated_at ON {table_name}")

    op.drop_table(agent_action_executions.name)
    op.drop_table(agent_executions.name)
    op.drop_table(captures.name)
