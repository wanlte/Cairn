from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.retrieval.schemas import (
    RetrievalAskRequest,
    RetrievalAskResponse,
    RetrievalIndexRequest,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from apps.api.retrieval.service import RetrievalService

router = APIRouter(prefix="/api/v1/retrieval", tags=["retrieval"])
service = RetrievalService()


@router.post("/index")
async def index_fragments(
    payload: RetrievalIndexRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await service.index(session, current_user.id, payload)
    await session.commit()
    return result


@router.post("/search", response_model=RetrievalSearchResponse)
async def search(
    payload: RetrievalSearchRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RetrievalSearchResponse:
    return await service.search(session, current_user.id, payload)


@router.post("/ask", response_model=RetrievalAskResponse)
async def ask(
    payload: RetrievalAskRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RetrievalAskResponse:
    return await service.ask(session, current_user.id, payload)
