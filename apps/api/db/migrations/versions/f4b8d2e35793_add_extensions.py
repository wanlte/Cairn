"""add extensions

Revision ID: f4b8d2e35793
Revises: e3a7c9d14682
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4b8d2e35793"
down_revision: str | Sequence[str] | None = "e3a7c9d14682"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "simulations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("scenario", sa.Text(), nullable=False),
        sa.Column("choice", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_simulation_user_created", "simulations", ["user_id", "created_at"])

    op.create_table(
        "daily_questions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "day", name="uq_daily_question_user_day"),
    )
    op.create_index("ix_daily_question_user_day", "daily_questions", ["user_id", "day"])


def downgrade() -> None:
    op.drop_index("ix_daily_question_user_day", table_name="daily_questions")
    op.drop_table("daily_questions")
    op.drop_index("ix_simulation_user_created", table_name="simulations")
    op.drop_table("simulations")
