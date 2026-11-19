from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.planning.schemas import (
    PlanGenerateRequest,
    PlanResponse,
    WeeklyFillCreate,
    WeeklyFillResponse,
)
from apps.api.planning.service import planning_service

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])


@router.post("/generate", response_model=PlanResponse, status_code=201)
async def generate_plan(
    payload: PlanGenerateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PlanResponse:
    result = await planning_service.generate(session, current_user.id, payload)
    await session.commit()
    return result


@router.get("/current", response_model=PlanResponse)
async def current_plan(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PlanResponse:
    return await planning_service.get_current(session, current_user.id)


@router.get("", response_model=list[PlanResponse])
async def list_plans(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[PlanResponse]:
    return await planning_service.list_plans(session, current_user.id, limit)


@router.post("/{blueprint_id}/weekly", response_model=WeeklyFillResponse, status_code=201)
async def fill_weekly(
    blueprint_id: int,
    payload: WeeklyFillCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WeeklyFillResponse:
    result = await planning_service.fill_weekly(
        session, current_user.id, blueprint_id, payload
    )
    await session.commit()
    return result
