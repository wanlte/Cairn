from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.db.models.extraction import Fragment
from apps.api.db.models.planning import PlanBlueprint, WeeklyFill
from apps.api.errors import AppError
from apps.api.gateway.factory import build_gateway_for_user
from apps.api.gateway.metering import session_meter
from apps.api.gateway.schemas import GatewayOptions, GatewayRequest, ResponseFormat
from apps.api.planning.schemas import (
    PLAN_JSON_SCHEMA,
    PlanGenerateRequest,
    PlanOutput,
    PlanResponse,
    WeeklyFillCreate,
    WeeklyFillResponse,
)
from apps.api.profile.service import profile_service
from apps.api.review.service import review_service
from apps.api.samples.coverage import sample_coverage

PROMPT_VERSION = "plan-v1"
_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "plan" / "v1.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


class PlanningService:
    async def generate(
        self,
        session: AsyncSession,
        user_id: int,
        request: PlanGenerateRequest,
    ) -> PlanResponse:
        fragments = (
            await session.execute(
                select(Fragment)
                .where(Fragment.user_id == user_id)
                .order_by(Fragment.id.desc())
                .limit(request.fragment_limit)
            )
        ).scalars().all()
        coverage = await sample_coverage(session, user_id, list(fragments))
        gateway, _credential_id, model, provider = await build_gateway_for_user(
            session, user_id, **request.gateway_kwargs()
        )

        payload: dict = {"目标": request.goal, "样本体检": coverage}
        try:
            profile = await profile_service.get_current(session, user_id)
            payload["画像"] = [
                {"方面": claim.group.value, "结论": claim.value}
                for claim in profile.claims
            ]
        except AppError:
            pass
        reports = await review_service.list_reports(session, user_id, 3)
        if reports:
            payload["最近复盘"] = [
                {"周期": report.period, "概览": report.overview}
                for report in reports[:2]
            ]

        settings = get_settings()
        gateway_request = GatewayRequest(
            task="plan",
            messages=[
                {"role": "system", "content": _load_prompt()},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            options=GatewayOptions(
                response_format=ResponseFormat.JSON_SCHEMA,
                output_schema=PLAN_JSON_SCHEMA,
                timeout_seconds=settings.gateway_read_timeout_review,
            ),
            user_id=user_id,
        )
        try:
            response = await gateway.complete(gateway_request, meter=session_meter(session))
            if not response.data:
                raise AppError("INVALID_PLAN_OUTPUT", "规划输出为空", 502)
            output = PlanOutput.model_validate(response.data)
        except Exception as exc:
            raise AppError("PLAN_GENERATION_FAILED", "规划生成失败", 502) from exc

        blueprint = PlanBlueprint(
            user_id=user_id,
            goal=request.goal,
            status="DONE",
            payload_json=output.model_dump(mode="json"),
            coverage_json=coverage,
            prompt_version=PROMPT_VERSION,
            model=model,
            provider=provider.value if provider else None,
        )
        session.add(blueprint)
        await session.flush()
        return await self._to_response(session, blueprint)

    async def _to_response(
        self, session: AsyncSession, blueprint: PlanBlueprint
    ) -> PlanResponse:
        fills = (
            await session.execute(
                select(WeeklyFill)
                .where(WeeklyFill.blueprint_id == blueprint.id)
                .order_by(WeeklyFill.created_at)
            )
        ).scalars().all()
        return PlanResponse(
            id=blueprint.id,
            user_id=blueprint.user_id,
            goal=blueprint.goal,
            status=blueprint.status,
            payload=blueprint.payload_json or {},
            coverage=blueprint.coverage_json or {},
            prompt_version=blueprint.prompt_version,
            model=blueprint.model,
            provider=blueprint.provider,
            created_at=blueprint.created_at,
            weekly_fills=[self._fill_response(fill) for fill in fills],
        )

    @staticmethod
    def _fill_response(fill: WeeklyFill) -> WeeklyFillResponse:
        return WeeklyFillResponse(
            id=fill.id,
            blueprint_id=fill.blueprint_id,
            week=fill.week,
            done=fill.done,
            blocked=fill.blocked,
            learning=fill.learning,
            created_at=fill.created_at,
        )

    async def get_current(self, session: AsyncSession, user_id: int) -> PlanResponse:
        blueprint = (
            await session.execute(
                select(PlanBlueprint)
                .where(PlanBlueprint.user_id == user_id)
                .order_by(PlanBlueprint.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not blueprint:
            raise AppError("PLAN_NOT_FOUND", "还没有规划蓝图", 404)
        return await self._to_response(session, blueprint)

    async def list_plans(
        self, session: AsyncSession, user_id: int, limit: int = 20
    ) -> list[PlanResponse]:
        blueprints = (
            await session.execute(
                select(PlanBlueprint)
                .where(PlanBlueprint.user_id == user_id)
                .order_by(PlanBlueprint.id.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [await self._to_response(session, item) for item in blueprints]

    async def fill_weekly(
        self,
        session: AsyncSession,
        user_id: int,
        blueprint_id: int,
        request: WeeklyFillCreate,
    ) -> WeeklyFillResponse:
        blueprint = await session.get(PlanBlueprint, blueprint_id)
        if not blueprint or blueprint.user_id != user_id:
            raise AppError("PLAN_NOT_FOUND", "找不到这份规划", 404, retryable=False)
        fill = (
            await session.execute(
                select(WeeklyFill).where(
                    WeeklyFill.user_id == user_id,
                    WeeklyFill.blueprint_id == blueprint_id,
                    WeeklyFill.week == request.week,
                )
            )
        ).scalar_one_or_none()
        if fill:
            fill.done = request.done
            fill.blocked = request.blocked
            fill.learning = request.learning
        else:
            fill = WeeklyFill(
                user_id=user_id,
                blueprint_id=blueprint_id,
                week=request.week,
                done=request.done,
                blocked=request.blocked,
                learning=request.learning,
            )
            session.add(fill)
        await session.flush()
        return self._fill_response(fill)


planning_service = PlanningService()
