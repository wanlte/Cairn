from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.insights.schemas import DriftCurveResponse, GraphResponse
from apps.api.insights.service import insights_service

router = APIRouter(prefix="/api/v1/insights", tags=["insights"])


@router.get("/drift", response_model=DriftCurveResponse)
async def drift_curve(
    group: str | None = Query(default=None, max_length=64),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DriftCurveResponse:
    return await insights_service.drift_curve(session, current_user.id, group)


@router.get("/graph", response_model=GraphResponse)
async def graph(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> GraphResponse:
    return await insights_service.graph(session, current_user.id)


@router.post("/graph/rebuild")
async def rebuild_graph(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    count = await insights_service.rebuild_graph(session, current_user.id)
    await session.commit()
    return {"edges": count}
