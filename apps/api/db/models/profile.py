from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db.base import Base


class ProfileSnapshot(Base):
    __tablename__ = "profile_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "period", name="uq_profile_user_period"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_profile_idempotency"),
        Index("ix_profile_snapshot_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_snapshot_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    coverage_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProfileClaim(Base):
    __tablename__ = "profile_claims"
    __table_args__ = (
        Index("ix_profile_claim_user_group", "user_id", "group_name"),
        Index("ix_profile_claim_snapshot", "snapshot_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("profile_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    group_name: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_fragment_ids: Mapped[list[Any]] = mapped_column(
        JSON, default=list, nullable=False
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    user_corrected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
