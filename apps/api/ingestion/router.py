from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.ingestion.schemas import (
    IngestCommitRequest,
    IngestionPreview,
    IngestPreviewRequest,
)
from apps.api.ingestion.service import ingestion_service

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


@router.post("/preview", response_model=IngestionPreview)
async def preview(
    payload: IngestPreviewRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> IngestionPreview:
    return ingestion_service.preview(current_user.id, payload)


@router.post("/commit")
async def commit(
    payload: IngestCommitRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await ingestion_service.commit(session, current_user.id, payload)
    await session.commit()
    return result


@router.get("/conversations")
async def list_conversations(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    return {"items": await ingestion_service.list_conversations(session, current_user.id)}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    return await ingestion_service.get_conversation(
        session, current_user.id, conversation_id
    )
