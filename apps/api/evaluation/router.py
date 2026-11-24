from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.evaluation.schemas import (
    DatasetInfo,
    EvaluationRunRequest,
    ExtractionEvalResponse,
    RetrievalEvalResponse,
    ReviewEvalResponse,
)
from apps.api.evaluation.service import evaluation_service, list_datasets

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation"])


@router.get("/datasets", response_model=list[DatasetInfo])
async def datasets() -> list[DatasetInfo]:
    return list_datasets()


@router.post("/extraction", response_model=ExtractionEvalResponse)
async def evaluate_extraction(
    payload: EvaluationRunRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ExtractionEvalResponse:
    result = await evaluation_service.evaluate_extraction(session, current_user.id, payload)
    await session.commit()
    return result


@router.post("/review", response_model=ReviewEvalResponse)
async def evaluate_review(
    payload: EvaluationRunRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ReviewEvalResponse:
    result = await evaluation_service.evaluate_review(session, current_user.id, payload)
    await session.commit()
    return result


@router.post("/retrieval", response_model=RetrievalEvalResponse)
async def evaluate_retrieval(
    payload: EvaluationRunRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RetrievalEvalResponse:
    result = await evaluation_service.evaluate_retrieval(session, current_user.id, payload)
    await session.commit()
    return result
