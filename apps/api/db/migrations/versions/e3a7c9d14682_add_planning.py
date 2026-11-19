"""add planning layer

Revision ID: e3a7c9d14682
Revises: d2f6a8b03571
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3a7c9d14682"
down_revision: str | Sequence[str] | None = "d2f6a8b03571"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_blueprints",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DONE"),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("coverage_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_plan_blueprint_user_created", "plan_blueprints", ["user_id", "created_at"])
    op.create_index("ix_plan_blueprint_user", "plan_blueprints", ["user_id"])

    op.create_table(
        "weekly_fills",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "blueprint_id",
            sa.BigInteger(),
            sa.ForeignKey("plan_blueprints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week", sa.String(16), nullable=False),
        sa.Column("done", sa.Text(), nullable=False, server_default=""),
        sa.Column("blocked", sa.Text(), nullable=False, server_default=""),
        sa.Column("learning", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "blueprint_id", "week", name="uq_weekly_fill_user_plan_week"),
    )
    op.create_index("ix_weekly_fill_user_week", "weekly_fills", ["user_id", "week"])


def downgrade() -> None:
    op.drop_index("ix_weekly_fill_user_week", table_name="weekly_fills")
    op.drop_table("weekly_fills")
    op.drop_index("ix_plan_blueprint_user", table_name="plan_blueprints")
    op.drop_index("ix_plan_blueprint_user_created", table_name="plan_blueprints")
    op.drop_table("plan_blueprints")
