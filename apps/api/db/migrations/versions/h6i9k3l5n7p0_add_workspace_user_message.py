"""add workspace task user message

Revision ID: h6i9k3l5n7p0
Revises: g5h8j2k4m6n8
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h6i9k3l5n7p0"
down_revision: str | Sequence[str] | None = "g5h8j2k4m6n8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_tasks",
        sa.Column("user_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_tasks", "user_message")
