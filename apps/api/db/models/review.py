from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
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


class ReviewReport(Base):
    __tablename__ = "review_reports"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_review_idempotency"),
        UniqueConstraint("user_id", "period", name="uq_review_user_period"),
        Index("ix_review_report_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    overview_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (Index("ix_review_item_report", "report_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    report_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("review_reports.id", ondelete="CASCADE"), nullable=False
    )
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    fragment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("fragments.id", ondelete="SET NULL"), nullable=True
    )
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attribution: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_fragment_ids: Mapped[list[Any]] = mapped_column(
        JSON, default=list, nullable=False
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    feedback_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ActionItem(Base):
    __tablename__ = "action_items"
    __table_args__ = (Index("ix_action_item_report", "report_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    report_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("review_reports.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    verification: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_fragment_ids: Mapped[list[Any]] = mapped_column(
        JSON, default=list, nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
