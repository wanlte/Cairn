from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UUID as UUIDType

from apps.api.config import get_settings
from apps.api.db.base import Base
from apps.api.gateway.schemas import MeteringRecord, redact_snippet


class LlmCallLog(Base):
    __tablename__ = "llm_call_log"
    __table_args__ = (
        Index("ix_llm_call_log_user_created", "user_id", "created_at"),
        Index("ix_llm_call_log_request", "request_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(UUIDType(as_uuid=False), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    cost_cny: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    fallback_from: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_response_snippet: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def _safe_request_id(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value))
        except (ValueError, AttributeError, TypeError):
            pass
    return str(uuid4())


def calculate_cost(prompt_tokens: int, completion_tokens: int) -> Decimal:
    settings = get_settings()
    input_cost = (
        Decimal(prompt_tokens)
        * Decimal(str(settings.gateway_cost_input_per_million_cny))
        / Decimal(1_000_000)
    )
    output_cost = (
        Decimal(completion_tokens)
        * Decimal(str(settings.gateway_cost_output_per_million_cny))
        / Decimal(1_000_000)
    )
    return (input_cost + output_cost).quantize(Decimal("0.000001"))


async def record_call(session: AsyncSession, record: MeteringRecord) -> LlmCallLog:
    snippet = redact_snippet(record.raw_snippet, limit=200)
    log = LlmCallLog(
        request_id=_safe_request_id(record.request_id),
        user_id=record.user_id,
        task_type=record.task,
        provider=record.provider.value,
        model=record.model,
        prompt_tokens=record.usage.prompt_tokens,
        completion_tokens=record.usage.completion_tokens,
        cost_cny=calculate_cost(
            record.usage.prompt_tokens, record.usage.completion_tokens
        ),
        latency_ms=record.latency_ms,
        retry_count=record.retry_count,
        fallback_from=record.fallback_from,
        status=record.status,
        error_code=record.error_code,
        raw_response_snippet=snippet,
    )
    session.add(log)
    await session.flush()
    return log


def log_to_dict(log: LlmCallLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "request_id": log.request_id,
        "task_type": log.task_type,
        "provider": log.provider,
        "model": log.model,
        "prompt_tokens": log.prompt_tokens,
        "completion_tokens": log.completion_tokens,
        "cost_cny": float(log.cost_cny or Decimal(0)),
        "latency_ms": log.latency_ms,
        "retry_count": log.retry_count,
        "fallback_from": log.fallback_from,
        "status": log.status,
        "error_code": log.error_code,
        "raw_response_snippet": log.raw_response_snippet,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }
