from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.db.models.extension import DailyQuestion, Simulation
from apps.api.db.models.platform import ConsentRecord, PairRelationship
from apps.api.errors import AppError
from apps.api.extensions.schemas import (
    DailyQuestionResponse,
    DecisionResponse,
    PairAnalysisResponse,
    SimulationResponse,
)
from apps.api.gateway.credential_selection import CredentialSelection
from apps.api.gateway.factory import build_gateway_for_user
from apps.api.gateway.schemas import GatewayOptions, GatewayRequest, ResponseFormat
from apps.api.profile.service import profile_service

_SIMULATE_PROMPT = "你是情景推演助手。只输出 JSON：{\"paths\":[{\"choice\":\"选择\",\"outcome\":\"结果\",\"signal\":\"信号\"}],\"advice\":\"一句建议\"}。所有文字用自然中文，不要出现字段标识符。"
_DECIDE_PROMPT = "你是决策代理。只输出 JSON：{\"suggestion\":\"建议做什么\",\"reasons\":[\"理由\"],\"first_step\":\"今天能做的第一步\"}。所有文字用自然中文，不要出现字段标识符。"
_DAILY_PROMPT = "你是每日一问教练。只输出 JSON：{\"question\":\"一个具体、能引发真实想法的问题\"}。问题要围绕用户的画像与最近记录，不要泛泛而谈，不要出现字段标识符。"
_PAIR_PROMPT = (
    "你是双人关系分析助手。双方已授权。只输出 JSON："
    "{\"summary\":\"总体判断\",\"mismatches\":[{\"situation\":\"冲突场景\",\"you\":\"你可能的反应\",\"them\":\"对方可能的反应\",\"repair\":\"怎么错位、如何补偿\"}]}。"
    "不要判断合不合适，只描述冲突时怎么错位。所有文字用自然中文。"
)


def _schema_for(kind: str) -> dict[str, Any]:
    if kind == "simulate":
        return {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "choice": {"type": "string"},
                            "outcome": {"type": "string"},
                            "signal": {"type": "string"},
                        },
                    },
                },
                "advice": {"type": "string"},
            },
        }
    if kind == "decide":
        return {
            "type": "object",
            "properties": {
                "suggestion": {"type": "string"},
                "reasons": {"type": "array", "items": {"type": "string"}},
                "first_step": {"type": "string"},
            },
        }
    if kind == "daily":
        return {"type": "object", "properties": {"question": {"type": "string"}}}
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "mismatches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "situation": {"type": "string"},
                        "you": {"type": "string"},
                        "them": {"type": "string"},
                        "repair": {"type": "string"},
                    },
                },
            },
        },
    }


class ExtensionsService:
    async def _complete(
        self,
        session: AsyncSession,
        user_id: int,
        request: CredentialSelection,
        task: str,
        system: str,
        payload: dict,
        schema_kind: str,
    ) -> dict[str, Any]:
        gateway, _credential_id, _model, _provider = await build_gateway_for_user(
            session, user_id, **request.gateway_kwargs()
        )
        settings = get_settings()
        gateway_request = GatewayRequest(
            task=task,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            options=GatewayOptions(
                response_format=ResponseFormat.JSON_SCHEMA,
                output_schema=_schema_for(schema_kind),
                timeout_seconds=settings.gateway_read_timeout_review,
            ),
            user_id=user_id,
        )
        response = await gateway.complete(gateway_request)
        if not response.data:
            raise AppError("EXTENSION_OUTPUT_EMPTY", "没有拿到结果", 502)
        return response.data

    async def _profile_context(self, session: AsyncSession, user_id: int) -> list[dict]:
        try:
            profile = await profile_service.get_current(session, user_id)
        except AppError:
            return []
        return [
            {"方面": claim.group.value, "结论": claim.value}
            for claim in profile.claims
        ]

    async def simulate(
        self,
        session: AsyncSession,
        user_id: int,
        scenario: str,
        choice: str,
        request: CredentialSelection,
    ) -> SimulationResponse:
        data = await self._complete(
            session,
            user_id,
            request,
            "simulate",
            _SIMULATE_PROMPT,
            {
                "场景": scenario,
                "已倾向的选择": choice,
                "画像": await self._profile_context(session, user_id),
            },
            "simulate",
        )
        simulation = Simulation(
            user_id=user_id,
            scenario=scenario,
            choice=choice,
            payload_json=data,
        )
        session.add(simulation)
        await session.flush()
        return SimulationResponse(
            id=simulation.id,
            scenario=simulation.scenario,
            choice=simulation.choice,
            payload=simulation.payload_json,
            created_at=simulation.created_at,
        )

    async def decide(
        self,
        session: AsyncSession,
        user_id: int,
        question: str,
        request: CredentialSelection,
    ) -> DecisionResponse:
        data = await self._complete(
            session,
            user_id,
            request,
            "decide",
            _DECIDE_PROMPT,
            {
                "问题": question,
                "画像": await self._profile_context(session, user_id),
            },
            "decide",
        )
        return DecisionResponse.model_validate(data)

    async def daily_question(
        self,
        session: AsyncSession,
        user_id: int,
        request: CredentialSelection | None = None,
    ) -> DailyQuestionResponse:
        today = date.today()
        existing = (
            await session.execute(
                select(DailyQuestion).where(
                    DailyQuestion.user_id == user_id,
                    DailyQuestion.day == today,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return self._daily_response(existing)

        question = "今天有一件事做完后，你最想先跟谁说？为什么是他？"
        if request is not None:
            data = await self._complete(
                session,
                user_id,
                request,
                "daily",
                _DAILY_PROMPT,
                {"画像": await self._profile_context(session, user_id)},
                "daily",
            )
            question = str(data.get("question") or question)
        record = DailyQuestion(user_id=user_id, day=today, question=question)
        session.add(record)
        await session.flush()
        return self._daily_response(record)

    async def answer_daily(
        self, session: AsyncSession, user_id: int, question_id: int, answer: str
    ) -> DailyQuestionResponse:
        record = await session.get(DailyQuestion, question_id)
        if not record or record.user_id != user_id:
            raise AppError("QUESTION_NOT_FOUND", "找不到这个问题", 404, retryable=False)
        record.answer = answer
        await session.flush()
        return self._daily_response(record)

    @staticmethod
    def _daily_response(record: DailyQuestion) -> DailyQuestionResponse:
        return DailyQuestionResponse(
            id=record.id,
            day=record.day,
            question=record.question,
            answer=record.answer,
            created_at=record.created_at,
        )

    async def pair_analysis(
        self,
        session: AsyncSession,
        user_id: int,
        pair_id: int,
        request: CredentialSelection,
    ) -> PairAnalysisResponse:
        pair = await session.get(PairRelationship, pair_id)
        if not pair or pair.status != "CONFIRMED":
            raise AppError("PAIR_NOT_CONFIRMED", "这段关系还没有双方确认", 403, retryable=False)
        if user_id not in (pair.user_a_id, pair.user_b_id):
            raise AppError("PAIR_FORBIDDEN", "你不在这一段关系里", 403, retryable=False)
        other_id = pair.user_b_id if user_id == pair.user_a_id else pair.user_a_id
        grants = (
            await session.execute(
                select(ConsentRecord).where(
                    ConsentRecord.user_id.in_([user_id, other_id]),
                    ConsentRecord.consent_type == "pair_analysis",
                    ConsentRecord.counterpart_id == other_id,
                    ConsentRecord.granted.is_(True),
                    ConsentRecord.revoked_at.is_(None),
                )
            )
        ).scalars().all()
        if len({row.user_id for row in grants}) < 2:
            raise AppError("PAIR_CONSENT_REQUIRED", "需要双方都授权后才能分析", 403, retryable=False)

        data = await self._complete(
            session,
            user_id,
            request,
            "pair",
            _PAIR_PROMPT,
            {
                "你的画像": await self._profile_context(session, user_id),
                "对方画像": await self._profile_context(session, other_id),
            },
            "pair",
        )
        return PairAnalysisResponse.model_validate(data)


extensions_service = ExtensionsService()
