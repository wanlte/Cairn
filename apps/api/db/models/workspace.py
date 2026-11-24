from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db.base import Base


class WorkspaceTask(Base):
    __tablename__ = "workspace_tasks"
    __table_args__ = (
        Index("ix_workspace_task_user_created", "user_id", "created_at"),
        Index("ix_workspace_task_user_status", "user_id", "status"),
        Index("ix_workspace_task_user_pinned", "user_id", "pinned"),
        Index("ix_workspace_task_user_archived", "user_id", "archived"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    intent: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    direction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recommend_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    user_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirm_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkspaceTaskEvent(Base):
    __tablename__ = "workspace_task_events"
    __table_args__ = (
        Index("ix_workspace_event_task_seq", "task_id", "seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    role_state: Mapped[str] = mapped_column(String(32), nullable=False, default="进行中")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    bubble_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
