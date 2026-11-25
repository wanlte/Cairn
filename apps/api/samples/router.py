from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.extraction import Fragment
from apps.api.db.models.sample import CounterfactualEntry
from apps.api.db.models.user import User
from apps.api.errors import AppError
from apps.api.samples.coverage import sample_coverage
from apps.api.samples.schemas import CounterfactualCreate, CounterfactualResponse

router = APIRouter(prefix="/api/v1/samples", tags=["samples"])


def _response(item: CounterfactualEntry) -> CounterfactualResponse:
    return CounterfactualResponse(
        id=item.id,
        prompt_type=item.prompt_type,
        content=item.content,
        source_label=item.source_label,
        created_at=item.created_at,
    )


@router.post("/counterfactuals", response_model=CounterfactualResponse, status_code=201)
async def create_counterfactual(
    payload: CounterfactualCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CounterfactualResponse:
    item = CounterfactualEntry(
        user_id=current_user.id,
        prompt_type=payload.prompt_type,
        content=payload.content.strip(),
        source_label=payload.source_label,
    )
    session.add(item)
    await session.commit()
    return _response(item)


@router.get("/counterfactuals", response_model=list[CounterfactualResponse])
async def list_counterfactuals(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[CounterfactualResponse]:
    rows = (
        await session.execute(
            select(CounterfactualEntry)
            .where(CounterfactualEntry.user_id == current_user.id)
            .order_by(CounterfactualEntry.created_at.desc())
        )
    ).scalars().all()
    return [_response(item) for item in rows]


@router.delete("/counterfactuals/{entry_id}", status_code=204)
async def delete_counterfactual(
    entry_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    item = await session.get(CounterfactualEntry, entry_id)
    if not item or item.user_id != current_user.id:
        raise AppError("COUNTERFACTUAL_NOT_FOUND", "找不到这条补录", 404, retryable=False)
    await session.delete(item)
    await session.commit()


@router.get("/coverage")
async def current_coverage(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    fragments = (
        await session.execute(
            select(Fragment)
            .where(Fragment.user_id == current_user.id)
            .order_by(Fragment.id.desc())
            .limit(200)
        )
    ).scalars().all()
    return await sample_coverage(session, current_user.id, list(fragments))
