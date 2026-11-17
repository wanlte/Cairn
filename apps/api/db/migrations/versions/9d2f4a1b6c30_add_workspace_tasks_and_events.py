"""add workspace tasks and events

Revision ID: 9d2f4a1b6c30
Revises: b57d8916e192
Create Date: 2026-11-17 23:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d2f4a1b6c30"
down_revision: str | Sequence[str] | None = "b57d8916e192"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_key", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="QUEUED"),
        sa.Column("intent", sa.String(length=32), nullable=False, server_default="free"),
        sa.Column("direction", sa.String(length=64), nullable=True),
        sa.Column("recommend_reason", sa.String(length=512), nullable=True),
        sa.Column("confirm_prompt", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("task_key", name="uq_workspace_task_key"),
    )
    op.create_index("ix_workspace_task_task_key", "workspace_tasks", ["task_key"], unique=True)
    op.create_index("ix_workspace_task_user_created", "workspace_tasks", ["user_id", "created_at"])
    op.create_index("ix_workspace_task_user_status", "workspace_tasks", ["user_id", "status"])

    op.create_table(
        "workspace_task_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=True),
        sa.Column("role_state", sa.String(length=32), nullable=False, server_default="进行中"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("bubble_id", sa.String(length=64), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=False, server_default="RUNNING"),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workspace_event_task_id", "workspace_task_events", ["task_id"])
    op.create_index("ix_workspace_event_task_seq", "workspace_task_events", ["task_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_workspace_event_task_seq", table_name="workspace_task_events")
    op.drop_index("ix_workspace_event_task_id", table_name="workspace_task_events")
    op.drop_table("workspace_task_events")
    op.drop_index("ix_workspace_task_user_status", table_name="workspace_tasks")
    op.drop_index("ix_workspace_task_user_created", table_name="workspace_tasks")
    op.drop_index("ix_workspace_task_task_key", table_name="workspace_tasks")
    op.drop_table("workspace_tasks")
