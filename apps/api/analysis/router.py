from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.analysis.service import analysis_service
from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.review.schemas import (
    AppealCreate,
    AppealResolve,
    AppealResponse,
    DesirabilityFlagResponse,
    EvidenceChainResponse,
)

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.get("/desirability", response_model=list[DesirabilityFlagResponse])
async def list_desirability(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[DesirabilityFlagResponse]:
    return await analysis_service.list_desirability(session, current_user.id)


@router.get("/evidence-chain/{item_id}", response_model=EvidenceChainResponse)
async def get_evidence_chain(
    item_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> EvidenceChainResponse:
    return await analysis_service.evidence_chain(session, current_user.id, item_id)


@router.post("/appeals", response_model=AppealResponse, status_code=201)
async def submit_appeal(
    payload: AppealCreate,
    item_id: int = Query(ge=1),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AppealResponse:
    result = await analysis_service.submit_appeal(
        session, current_user.id, item_id, payload.reason
    )
    await session.commit()
    return result


@router.get("/appeals", response_model=list[AppealResponse])
async def list_appeals(
    status: str | None = Query(default=None, pattern="^(PENDING|ACCEPTED|REJECTED)$"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[AppealResponse]:
    return await analysis_service.list_appeals(session, current_user.id, status)


@router.post("/appeals/{appeal_id}/resolve", response_model=AppealResponse)
async def resolve_appeal(
    appeal_id: int,
    payload: AppealResolve,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AppealResponse:
    result = await analysis_service.resolve_appeal(
        session, current_user.id, appeal_id, payload.decision, payload.note
    )
    await session.commit()
    return result
