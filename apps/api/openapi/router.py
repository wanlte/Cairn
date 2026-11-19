from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.base import get_session
from apps.api.extensions.schemas import SimulationRequest, SimulationResponse
from apps.api.extensions.service import extensions_service
from apps.api.platform.deps import PlatformIdentity, require_scope
from apps.api.profile.schemas import ProfileSnapshotResponse
from apps.api.profile.service import profile_service
from apps.api.review.schemas import ReviewReportResponse
from apps.api.review.service import review_service

router = APIRouter(prefix="/api/v1/open", tags=["open"])


@router.get("/profile", response_model=ProfileSnapshotResponse)
async def open_profile(
    identity: PlatformIdentity = Depends(require_scope("profile:read")),
    session: AsyncSession = Depends(get_session),
) -> ProfileSnapshotResponse:
    return await profile_service.get_current(session, identity.user_id)


@router.get("/reviews", response_model=list[ReviewReportResponse])
async def open_reviews(
    identity: PlatformIdentity = Depends(require_scope("review:read")),
    session: AsyncSession = Depends(get_session),
) -> list[ReviewReportResponse]:
    return await review_service.list_reports(session, identity.user_id, 20)


@router.post("/simulate", response_model=SimulationResponse, status_code=201)
async def open_simulate(
    payload: SimulationRequest,
    identity: PlatformIdentity = Depends(require_scope("simulate:write")),
    session: AsyncSession = Depends(get_session),
) -> SimulationResponse:
    result = await extensions_service.simulate(
        session, identity.user_id, payload.scenario, payload.choice, payload
    )
    await session.commit()
    return result
