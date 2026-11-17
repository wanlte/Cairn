from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.review.schemas import (
    ReviewCreateRequest,
    ReviewFeedbackRequest,
    ReviewItemResponse,
    ReviewReportResponse,
)
from apps.api.review.service import review_service

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])


@router.post("", response_model=ReviewReportResponse, status_code=201)
async def create_review(
    payload: ReviewCreateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ReviewReportResponse:
    result = await review_service.create_report(session, current_user.id, payload)
    await session.commit()
    return result


@router.get("", response_model=list[ReviewReportResponse])
async def list_reviews(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ReviewReportResponse]:
    return await review_service.list_reports(session, current_user.id, limit)


@router.get("/{report_id}", response_model=ReviewReportResponse)
async def get_review(
    report_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ReviewReportResponse:
    return await review_service.get_report(session, current_user.id, report_id)


@router.post("/items/{item_id}/feedback", response_model=ReviewItemResponse)
async def feedback_review_item(
    item_id: int,
    payload: ReviewFeedbackRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ReviewItemResponse:
    result = await review_service.add_feedback(session, current_user.id, item_id, payload)
    await session.commit()
    return result
