"""add platform foundation

Revision ID: a7c3e9f14280
Revises: 9d2f4a1b6c30
Create Date: 2026-11-19 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e9f14280"
down_revision: str | Sequence[str] | None = "9d2f4a1b6c30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_api_keys",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("key_prefix", sa.String(length=24), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("scopes_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("key_hash", name="uq_platform_api_key_hash"),
    )
    op.create_index("ix_platform_api_key_key_prefix", "platform_api_keys", ["key_prefix"])
    op.create_index("ix_platform_api_key_user", "platform_api_keys", ["user_id", "created_at"])

    op.create_table(
        "platform_audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False, server_default="USER"),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=96), nullable=False),
        sa.Column("target_type", sa.String(length=96), nullable=True),
        sa.Column("target_id", sa.String(length=128), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_platform_audit_action", "platform_audit_logs", ["action", "created_at"])
    op.create_index("ix_platform_audit_user_created", "platform_audit_logs", ["user_id", "created_at"])

    op.create_table(
        "platform_consents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("consent_type", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("counterpart_id", sa.BigInteger(), nullable=True),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "consent_type", "counterpart_id", name="uq_platform_consent_pair"),
    )
    op.create_index("ix_platform_consent_user_type", "platform_consents", ["user_id", "consent_type"])

    op.create_table(
        "platform_pair_relationships",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_a_id", sa.BigInteger(), nullable=False),
        sa.Column("user_b_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_a_id", "user_b_id", name="uq_platform_pair_users"),
    )
    op.create_index("ix_platform_pair_status", "platform_pair_relationships", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_platform_pair_status", table_name="platform_pair_relationships")
    op.drop_table("platform_pair_relationships")
    op.drop_index("ix_platform_consent_user_type", table_name="platform_consents")
    op.drop_table("platform_consents")
    op.drop_index("ix_platform_audit_user_created", table_name="platform_audit_logs")
    op.drop_index("ix_platform_audit_action", table_name="platform_audit_logs")
    op.drop_table("platform_audit_logs")
    op.drop_index("ix_platform_api_key_user", table_name="platform_api_keys")
    op.drop_index("ix_platform_api_key_key_prefix", table_name="platform_api_keys")
    op.drop_table("platform_api_keys")
