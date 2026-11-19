from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db.base import Base


class AnalysisAppeal(Base):
    __tablename__ = "analysis_appeals"
    __table_args__ = (
        UniqueConstraint("item_id", name="uq_analysis_appeal_item"),
        Index("ix_analysis_appeal_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("review_items.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DesirabilityFlag(Base):
    __tablename__ = "desirability_flags"
    __table_args__ = (
        UniqueConstraint("user_id", "fragment_id", name="uq_desirability_user_fragment"),
        Index("ix_desirability_user_score", "user_id", "score"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    fragment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fragments.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[Any] = mapped_column(Numeric(5, 4), nullable=False)
    signals_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
