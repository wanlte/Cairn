from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.errors import AppError
from apps.api.gateway.metering import LlmCallLog, log_to_dict


def _bucket_expr(granularity: str):
    if granularity == "hour":
        return func.to_char(LlmCallLog.created_at, "YYYY-MM-DD HH24:00")
    return func.to_char(LlmCallLog.created_at, "YYYY-MM-DD")


async def usage_summary(
    session: AsyncSession, user_id: int, granularity: str = "day"
) -> list[dict]:
    bucket = _bucket_expr(granularity).label("bucket")
    stmt: Select = (
        select(
            bucket,
            LlmCallLog.task_type,
            LlmCallLog.provider,
            LlmCallLog.model,
            func.count(LlmCallLog.id).label("calls"),
            func.coalesce(func.sum(LlmCallLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(LlmCallLog.completion_tokens), 0).label(
                "completion_tokens"
            ),
            func.coalesce(func.sum(LlmCallLog.cost_cny), 0).label("cost_cny"),
        )
        .where(LlmCallLog.user_id == user_id)
        .group_by(bucket, LlmCallLog.task_type, LlmCallLog.provider, LlmCallLog.model)
        .order_by(bucket, LlmCallLog.task_type, LlmCallLog.provider)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "bucket": row.bucket,
            "task_type": row.task_type,
            "provider": row.provider,
            "model": row.model,
            "calls": row.calls,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "cost_cny": float(row.cost_cny),
        }
        for row in rows
    ]


async def usage_calls(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> dict:
    if limit < 1 or limit > 200:
        raise AppError("VALIDATION_ERROR", "limit 必须在 1 到 200 之间", 422)
    stmt = select(LlmCallLog).where(LlmCallLog.user_id == user_id)
    if cursor:
        try:
            stmt = stmt.where(LlmCallLog.id < int(cursor))
        except ValueError as exc:
            raise AppError("VALIDATION_ERROR", "cursor 无效", 422) from exc
    stmt = stmt.order_by(LlmCallLog.id.desc()).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    has_more = len(rows) > limit
    items = [log_to_dict(row) for row in rows[:limit]]
    return {
        "items": items,
        "next_cursor": str(items[-1]["id"]) if has_more and items else None,
    }
