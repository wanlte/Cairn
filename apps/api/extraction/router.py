from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.extraction.schemas import (
    ExtractionCreateRequest,
    ExtractionRunResponse,
    FragmentKind,
    FragmentResponse,
)
from apps.api.extraction.service import extraction_service

router = APIRouter(prefix="/api/v1/extraction", tags=["extraction"])


@router.post("/runs", response_model=ExtractionRunResponse, status_code=201)
async def start_extraction(
    payload: ExtractionCreateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ExtractionRunResponse:
    result = await extraction_service.start(session, current_user.id, payload)
    await session.commit()
    return result


@router.get("/runs", response_model=list[ExtractionRunResponse])
async def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ExtractionRunResponse]:
    return await extraction_service.list_runs(session, current_user.id, limit)


@router.get("/runs/{run_id}", response_model=ExtractionRunResponse)
async def get_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ExtractionRunResponse:
    return await extraction_service.get_run(session, current_user.id, run_id)


@router.get("/fragments", response_model=list[FragmentResponse])
async def list_fragments(
    run_id: int | None = None,
    kind: FragmentKind | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[FragmentResponse]:
    return await extraction_service.list_fragments(
        session, current_user.id, run_id=run_id, kind=kind, limit=limit
    )
