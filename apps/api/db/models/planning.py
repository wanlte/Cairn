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


class PlanBlueprint(Base):
    __tablename__ = "plan_blueprints"
    __table_args__ = (
        Index("ix_plan_blueprint_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="DONE", nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    coverage_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WeeklyFill(Base):
    __tablename__ = "weekly_fills"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "blueprint_id", "week", name="uq_weekly_fill_user_plan_week"
        ),
        Index("ix_weekly_fill_user_week", "user_id", "week"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    blueprint_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("plan_blueprints.id", ondelete="CASCADE"), nullable=False
    )
    week: Mapped[str] = mapped_column(String(16), nullable=False)
    done: Mapped[str] = mapped_column(Text, default="", nullable=False)
    blocked: Mapped[str] = mapped_column(Text, default="", nullable=False)
    learning: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
