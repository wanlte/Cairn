"""add workspace task pinned and archived flags

Revision ID: j7k4l6n8p1q2
Revises: h6i9k3l5n7p0
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j7k4l6n8p1q2"
down_revision: str | Sequence[str] | None = "h6i9k3l5n7p0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_tasks",
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "workspace_tasks",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_workspace_task_user_pinned", "workspace_tasks", ["user_id", "pinned"]
    )
    op.create_index(
        "ix_workspace_task_user_archived", "workspace_tasks", ["user_id", "archived"]
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_task_user_archived", table_name="workspace_tasks")
    op.drop_index("ix_workspace_task_user_pinned", table_name="workspace_tasks")
    op.drop_column("workspace_tasks", "archived")
    op.drop_column("workspace_tasks", "pinned")
