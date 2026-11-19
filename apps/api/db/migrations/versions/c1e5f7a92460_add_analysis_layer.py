"""add analysis layer

Revision ID: c1e5f7a92460
Revises: b8d4eaf25391
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1e5f7a92460"
down_revision: str | Sequence[str] | None = "b8d4eaf25391"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("review_items", sa.Column("confidence_low", sa.Numeric(5, 4), nullable=True))
    op.add_column("review_items", sa.Column("confidence_high", sa.Numeric(5, 4), nullable=True))
    op.add_column("review_items", sa.Column("reasoning_chain_json", sa.JSON(), nullable=True))
    op.add_column(
        "review_items",
        sa.Column("conflict_with_json", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "review_items",
        sa.Column("appeal_status", sa.String(16), nullable=False, server_default="NONE"),
    )

    op.create_table(
        "analysis_appeals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "item_id",
            sa.BigInteger(),
            sa.ForeignKey("review_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("item_id", name="uq_analysis_appeal_item"),
    )
    op.create_index("ix_analysis_appeal_user_status", "analysis_appeals", ["user_id", "status"])
    op.create_index("ix_analysis_appeal_user", "analysis_appeals", ["user_id"])

    op.create_table(
        "desirability_flags",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "fragment_id",
            sa.BigInteger(),
            sa.ForeignKey("fragments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column("signals_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "fragment_id", name="uq_desirability_user_fragment"),
    )
    op.create_index("ix_desirability_user_score", "desirability_flags", ["user_id", "score"])
    op.create_index("ix_desirability_user", "desirability_flags", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_desirability_user", table_name="desirability_flags")
    op.drop_index("ix_desirability_user_score", table_name="desirability_flags")
    op.drop_table("desirability_flags")
    op.drop_index("ix_analysis_appeal_user", table_name="analysis_appeals")
    op.drop_index("ix_analysis_appeal_user_status", table_name="analysis_appeals")
    op.drop_table("analysis_appeals")
    op.drop_column("review_items", "appeal_status")
    op.drop_column("review_items", "conflict_with_json")
    op.drop_column("review_items", "reasoning_chain_json")
    op.drop_column("review_items", "confidence_high")
    op.drop_column("review_items", "confidence_low")
