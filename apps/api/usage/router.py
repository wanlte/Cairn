from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.usage.service import usage_calls, usage_summary

router = APIRouter(prefix="/api/v1/usage", tags=["usage"])


@router.get("/summary")
async def get_usage_summary(
    granularity: str = Query(default="day", pattern="^(day|hour)$"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    items = await usage_summary(session, current_user.id, granularity)
    return {"granularity": granularity, "items": items}


@router.get("/calls")
async def get_usage_calls(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    return await usage_calls(session, current_user.id, limit=limit, cursor=cursor)
