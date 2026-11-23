from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.metrics.schemas import (
    BehaviorMetrics,
    CostMetrics,
    EventCreate,
    EventResponse,
    MetricsOverview,
    QualityMetrics,
    SecurityMetrics,
    SystemMetrics,
    ValueMetrics,
)
from apps.api.metrics.service import metrics_service

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


@router.get("/overview", response_model=MetricsOverview)
async def overview(
    window_days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MetricsOverview:
    return await metrics_service.overview(session, current_user.id, window_days)


@router.get("/system", response_model=SystemMetrics)
async def system_metrics(
    window_days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> SystemMetrics:
    result = await metrics_service.overview(session, current_user.id, window_days)
    return result.system


@router.get("/quality", response_model=QualityMetrics)
async def quality_metrics(
    window_days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> QualityMetrics:
    result = await metrics_service.overview(session, current_user.id, window_days)
    return result.quality


@router.get("/cost", response_model=CostMetrics)
async def cost_metrics(
    window_days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CostMetrics:
    result = await metrics_service.overview(session, current_user.id, window_days)
    return result.cost


@router.get("/behavior", response_model=BehaviorMetrics)
async def behavior_metrics(
    window_days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> BehaviorMetrics:
    result = await metrics_service.overview(session, current_user.id, window_days)
    return result.behavior


@router.get("/value", response_model=ValueMetrics)
async def value_metrics(
    window_days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ValueMetrics:
    result = await metrics_service.overview(session, current_user.id, window_days)
    return result.value


@router.get("/security", response_model=SecurityMetrics)
async def security_metrics(
    window_days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> SecurityMetrics:
    result = await metrics_service.overview(session, current_user.id, window_days)
    return result.security


@router.post("/events", response_model=EventResponse, status_code=201)
async def record_event(
    payload: EventCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> EventResponse:
    result = await metrics_service.record_event(
        session, current_user.id, payload.event_type, payload.payload
    )
    await session.commit()
    return result
