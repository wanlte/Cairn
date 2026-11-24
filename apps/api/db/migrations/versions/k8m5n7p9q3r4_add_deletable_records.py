"""add soft delete and conversation links for deletable records

Revision ID: k8m5n7p9q3r4
Revises: j7k4l6n8p1q2
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k8m5n7p9q3r4"
down_revision: str | Sequence[str] | None = "j7k4l6n8p1q2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "review_reports",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_review_report_user_deleted", "review_reports", ["user_id", "is_deleted"])

    op.add_column(
        "workspace_tasks",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "workspace_tasks",
        sa.Column("conversation_ids_json", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("workspace_tasks", "conversation_ids_json")
    op.drop_column("workspace_tasks", "is_deleted")
    op.drop_index("ix_review_report_user_deleted", table_name="review_reports")
    op.drop_column("review_reports", "is_deleted")
