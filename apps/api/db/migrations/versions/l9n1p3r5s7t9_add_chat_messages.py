"""add chat messages for direct streaming conversations

Revision ID: l9n1p3r5s7t9
Revises: k8m5n7p9q3r4
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l9n1p3r5s7t9"
down_revision: str | Sequence[str] | None = "k8m5n7p9q3r4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_message_user_session_id",
        "chat_messages",
        ["user_id", "session_id", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_message_user_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")
