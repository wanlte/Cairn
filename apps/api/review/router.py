from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.metrics import UserEvent
from apps.api.db.models.user import User
from apps.api.review.schemas import (
    ActionItemResponse,
    ActionItemStatus,
    ActionItemVerifyRequest,
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
    session.add(
        UserEvent(
            user_id=current_user.id,
            event_type="review_generated",
            payload_json={"period": result.period},
        )
    )
    await session.commit()
    return result


@router.get("", response_model=list[ReviewReportResponse])
async def list_reviews(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ReviewReportResponse]:
    return await review_service.list_reports(session, current_user.id, limit)


@router.get("/action-items", response_model=list[ActionItemResponse])
async def list_action_items(
    status: ActionItemStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ActionItemResponse]:
    return await review_service.list_action_items(
        session, current_user.id, status=status, limit=limit
    )


@router.post("/action-items/{action_id}/verify", response_model=ActionItemResponse)
async def verify_action_item(
    action_id: int,
    payload: ActionItemVerifyRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ActionItemResponse:
    result = await review_service.verify_action_item(
        session, current_user.id, action_id, payload
    )
    await session.commit()
    return result


@router.post("/action-items/{action_id}/reopen", response_model=ActionItemResponse)
async def reopen_action_item(
    action_id: int,
    payload: ActionItemVerifyRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ActionItemResponse:
    result = await review_service.reopen_action_item(
        session, current_user.id, action_id, payload
    )
    await session.commit()
    return result


@router.get("/{report_id}/export", response_class=PlainTextResponse)
async def export_review(
    report_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> str:
    return await review_service.export_report_markdown(
        session, current_user.id, report_id
    )


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
