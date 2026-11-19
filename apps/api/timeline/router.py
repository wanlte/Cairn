from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.timeline.schemas import TimelineEventType, TimelineResponse
from apps.api.timeline.service import timeline_service

router = APIRouter(prefix="/api/v1/timeline", tags=["timeline"])


@router.get("/events", response_model=TimelineResponse)
async def events(
    event_types: list[TimelineEventType] | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TimelineResponse:
    return await timeline_service.build(
        session,
        current_user.id,
        event_types=event_types,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
