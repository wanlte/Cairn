"""add relation edges

Revision ID: d2f6a8b03571
Revises: c1e5f7a92460
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2f6a8b03571"
down_revision: str | Sequence[str] | None = "c1e5f7a92460"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "relation_edges",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_label", sa.String(128), nullable=False),
        sa.Column("target_label", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("weight", sa.Numeric(8, 2), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "source_label", "target_label", "kind", name="uq_relation_edge_pair"
        ),
    )
    op.create_index("ix_relation_edge_user_kind", "relation_edges", ["user_id", "kind"])
    op.create_index("ix_relation_edge_user", "relation_edges", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_relation_edge_user", table_name="relation_edges")
    op.drop_index("ix_relation_edge_user_kind", table_name="relation_edges")
    op.drop_table("relation_edges")
