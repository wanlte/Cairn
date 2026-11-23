"""add metrics user events

Revision ID: g5h8j2k4m6n8
Revises: f4b8d2e35793
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g5h8j2k4m6n8"
down_revision: str | Sequence[str] | None = "f4b8d2e35793"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_event_user_type_created", "user_events", ["user_id", "event_type", "created_at"])
    op.create_index("ix_user_events_user_id", "user_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_events_user_id", table_name="user_events")
    op.drop_index("ix_user_event_user_type_created", table_name="user_events")
    op.drop_table("user_events")
