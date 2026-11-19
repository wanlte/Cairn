from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.extensions.schemas import (
    DailyAnswerRequest,
    DailyQuestionResponse,
    DecisionRequest,
    DecisionResponse,
    PairAnalysisRequest,
    PairAnalysisResponse,
    SimulationRequest,
    SimulationResponse,
)
from apps.api.extensions.service import extensions_service

router = APIRouter(prefix="/api/v1/extensions", tags=["extensions"])


@router.post("/simulate", response_model=SimulationResponse, status_code=201)
async def simulate(
    payload: SimulationRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> SimulationResponse:
    result = await extensions_service.simulate(
        session, current_user.id, payload.scenario, payload.choice, payload
    )
    await session.commit()
    return result


@router.post("/decide", response_model=DecisionResponse)
async def decide(
    payload: DecisionRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DecisionResponse:
    return await extensions_service.decide(
        session, current_user.id, payload.question, payload
    )


@router.get("/daily", response_model=DailyQuestionResponse)
async def daily_question(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DailyQuestionResponse:
    result = await extensions_service.daily_question(session, current_user.id)
    await session.commit()
    return result


@router.post("/daily/{question_id}/answer", response_model=DailyQuestionResponse)
async def answer_daily(
    question_id: int,
    payload: DailyAnswerRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DailyQuestionResponse:
    result = await extensions_service.answer_daily(
        session, current_user.id, question_id, payload.answer
    )
    await session.commit()
    return result


@router.post("/pair-analysis", response_model=PairAnalysisResponse)
async def pair_analysis(
    payload: PairAnalysisRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PairAnalysisResponse:
    return await extensions_service.pair_analysis(
        session, current_user.id, payload.pair_id, payload
    )
