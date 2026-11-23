from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.metrics import UserEvent
from apps.api.db.models.user import User
from apps.api.profile.schemas import (
    ProfileClaimResponse,
    ProfileClaimUpsert,
    ProfileDiffResponse,
    ProfileGenerateRequest,
    ProfileSnapshotResponse,
)
from apps.api.profile.service import profile_service

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


@router.post("/generate", response_model=ProfileSnapshotResponse, status_code=201)
async def generate_profile(
    payload: ProfileGenerateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ProfileSnapshotResponse:
    result = await profile_service.generate(session, current_user.id, payload)
    session.add(
        UserEvent(
            user_id=current_user.id,
            event_type="profile_generated",
            payload_json={"period": result.period},
        )
    )
    await session.commit()
    return result


@router.get("/current", response_model=ProfileSnapshotResponse)
async def get_current_profile(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ProfileSnapshotResponse:
    return await profile_service.get_current(session, current_user.id)


@router.get("/snapshots", response_model=list[ProfileSnapshotResponse])
async def list_snapshots(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ProfileSnapshotResponse]:
    return await profile_service.list_snapshots(session, current_user.id, limit)


@router.get("/snapshot", response_model=ProfileSnapshotResponse)
async def get_snapshot_by_period(
    period: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ProfileSnapshotResponse:
    return await profile_service.get_by_period(session, current_user.id, period)


@router.get("/snapshot/export", response_class=PlainTextResponse)
async def export_snapshot(
    period: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> str:
    return await profile_service.export_markdown(session, current_user.id, period)


@router.get("/diff", response_model=ProfileDiffResponse)
async def diff_profile(
    from_period: str,
    to_period: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ProfileDiffResponse:
    return await profile_service.diff(session, current_user.id, from_period, to_period)


@router.put("/claims", response_model=ProfileClaimResponse)
async def upsert_claim(
    payload: ProfileClaimUpsert,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ProfileClaimResponse:
    result = await profile_service.upsert_claim(session, current_user.id, payload)
    await session.commit()
    return result


@router.delete("/claims/{claim_id}", status_code=204)
async def delete_claim(
    claim_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    await profile_service.delete_claim(session, current_user.id, claim_id)
    await session.commit()
