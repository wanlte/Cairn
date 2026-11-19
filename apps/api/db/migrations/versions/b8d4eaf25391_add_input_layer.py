"""add input layer

Revision ID: b8d4eaf25391
Revises: a7c3e9f14280
Create Date: 2026-11-19 21:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8d4eaf25391"
down_revision: str | Sequence[str] | None = "a7c3e9f14280"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "review_reports",
        sa.Column("coverage_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "profile_snapshots",
        sa.Column("coverage_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "counterfactual_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("prompt_type", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_label", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_counterfactual_user_created", "counterfactual_entries", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_counterfactual_user_created", table_name="counterfactual_entries")
    op.drop_table("counterfactual_entries")
    op.drop_column("profile_snapshots", "coverage_json")
    op.drop_column("review_reports", "coverage_json")
