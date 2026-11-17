from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from apps.api.config import get_settings
from apps.api.db.models.extraction import Fragment
from apps.api.db.models.review import ActionItem, ReviewItem, ReviewReport
from apps.api.errors import AppError
from apps.api.gateway.factory import build_gateway_for_user
from apps.api.gateway.schemas import (
    GatewayOptions,
    GatewayRequest,
    ResponseFormat,
)
from apps.api.review.schemas import (
    REVIEW_JSON_SCHEMA,
    ReviewCreateRequest,
    ReviewFeedbackRequest,
    ReviewItemResponse,
    ReviewOutput,
    ReviewReportResponse,
)

PROMPT_VERSION = "review-v1"
_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "review" / "v1.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if hasattr(code, "value"):
        return str(code.value)
    if isinstance(exc, AppError):
        return exc.code
    return exc.__class__.__name__


class ReviewService:
    async def create_report(
        self,
        session: AsyncSession,
        user_id: int,
        request: ReviewCreateRequest,
    ) -> ReviewReportResponse:
        if request.idempotency_key:
            existing = (
                await session.execute(
                    select(ReviewReport).where(
                        ReviewReport.user_id == user_id,
                        ReviewReport.idempotency_key == request.idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return await self._to_response(session, existing)

        existing_period = (
            await session.execute(
                select(ReviewReport).where(
                    ReviewReport.user_id == user_id,
                    ReviewReport.period == request.period,
                )
            )
        ).scalar_one_or_none()
        if existing_period:
            raise AppError("REVIEW_PERIOD_EXISTS", "该周期复盘已存在", 409)

        stmt = select(Fragment).where(Fragment.user_id == user_id)
        if request.conversation_id is not None:
            stmt = stmt.where(Fragment.conversation_id == request.conversation_id)
        fragments = (
            await session.execute(stmt.order_by(Fragment.id.desc()).limit(request.max_fragments))
        ).scalars().all()
        if not fragments:
            raise AppError("FRAGMENT_EMPTY", "没有可用于复盘的碎片", 422)

        gateway, _credential_id, model, provider = await build_gateway_for_user(
            session,
            user_id,
            credential_id=request.credential_id,
            provider=request.provider,
            model=request.model,
        )

        report = ReviewReport(
            user_id=user_id,
            period=request.period,
            status="RUNNING",
            overview_json={},
            prompt_version=PROMPT_VERSION,
            model=model,
            provider=provider.value if provider else None,
            idempotency_key=request.idempotency_key,
        )
        session.add(report)
        await session.flush()

        settings = get_settings()
        fragment_payload = [
            {"id": item.id, "kind": item.kind, "payload": item.payload_json}
            for item in fragments
        ]
        gateway_request = GatewayRequest(
            task="review",
            messages=[
                {"role": "system", "content": _load_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"period": request.period, "fragments": fragment_payload},
                        ensure_ascii=False,
                    ),
                },
            ],
            options=GatewayOptions(
                response_format=ResponseFormat.JSON_SCHEMA,
                output_schema=REVIEW_JSON_SCHEMA,
                timeout_seconds=settings.gateway_read_timeout_review,
            ),
            user_id=user_id,
        )

        try:
            response = await gateway.complete(gateway_request)
            if not response.data:
                raise AppError("INVALID_REVIEW_OUTPUT", "复盘输出为空", 502)
            output = ReviewOutput.model_validate(response.data)
        except Exception as exc:  # noqa: BLE001 - 失败要落库，不能静默丢弃
            report.status = "FAILED"
            report.error_code = _error_code(exc)
            await session.flush()
            return await self._to_response(session, report)

        valid_ids = {item.id for item in fragments}
        output = self._enforce_evidence(output, valid_ids)
        report.overview_json = output.overview.model_dump(mode="json")
        report.status = "DONE"
        await session.flush()

        for item in output.key_events:
            session.add(
                ReviewItem(
                    user_id=user_id,
                    report_id=report.id,
                    section="key_event",
                    fragment_id=item.fragment_id,
                    evidence_fragment_ids=[item.fragment_id],
                    payload_json=item.model_dump(mode="json"),
                )
            )
        for item in output.judgments:
            session.add(
                ReviewItem(
                    user_id=user_id,
                    report_id=report.id,
                    section="judgment",
                    fragment_id=item.fragment_id,
                    verdict=item.verdict.value,
                    attribution=item.attribution.value,
                    evidence_fragment_ids=item.evidence_fragment_ids,
                    payload_json=item.model_dump(mode="json"),
                )
            )
        for item in output.cognitive_changes:
            session.add(
                ReviewItem(
                    user_id=user_id,
                    report_id=report.id,
                    section="cognitive_change",
                    evidence_fragment_ids=item.evidence_fragment_ids,
                    payload_json=item.model_dump(mode="json"),
                )
            )
        for item in output.action_items[:3]:
            session.add(
                ActionItem(
                    user_id=user_id,
                    report_id=report.id,
                    content=item.content,
                    verification=item.verification,
                    evidence_fragment_ids=item.evidence_fragment_ids,
                )
            )
        await session.flush()
        return await self._to_response(session, report)

    @staticmethod
    def _enforce_evidence(output: ReviewOutput, valid_ids: set[int]) -> ReviewOutput:
        def valid(items: list[int]) -> list[int]:
            return [item for item in items if item in valid_ids]

        output.key_events = [item for item in output.key_events if item.fragment_id in valid_ids]
        output.judgments = [
            item
            for item in output.judgments
            if valid(item.evidence_fragment_ids) and item.fragment_id in valid_ids
        ]
        for item in output.judgments:
            item.evidence_fragment_ids = valid(item.evidence_fragment_ids)
        output.cognitive_changes = [
            item
            for item in output.cognitive_changes
            if valid(item.evidence_fragment_ids)
        ]
        for item in output.cognitive_changes:
            item.evidence_fragment_ids = valid(item.evidence_fragment_ids)
        output.action_items = [
            item for item in output.action_items if item.verification.strip()
        ][:3]
        for item in output.action_items:
            item.evidence_fragment_ids = valid(item.evidence_fragment_ids)
        return output

    async def _to_response(
        self, session: AsyncSession, report: ReviewReport
    ) -> ReviewReportResponse:
        items = (
            await session.execute(
                select(ReviewItem)
                .where(ReviewItem.report_id == report.id)
                .order_by(ReviewItem.id)
            )
        ).scalars().all()
        actions = (
            await session.execute(
                select(ActionItem)
                .where(ActionItem.report_id == report.id)
                .order_by(ActionItem.id)
            )
        ).scalars().all()
        return ReviewReportResponse(
            id=report.id,
            user_id=report.user_id,
            period=report.period,
            status=report.status,
            overview=report.overview_json,
            prompt_version=report.prompt_version,
            model=report.model,
            provider=report.provider,
            error_code=report.error_code,
            created_at=report.created_at,
            items=[
                ReviewItemResponse(
                    id=item.id,
                    section=item.section,
                    verdict=item.verdict,
                    attribution=item.attribution,
                    fragment_id=item.fragment_id,
                    evidence_fragment_ids=item.evidence_fragment_ids,
                    payload=item.payload_json,
                    feedback=item.feedback_json,
                )
                for item in items
            ],
            action_items=[
                {
                    "id": action.id,
                    "content": action.content,
                    "verification": action.verification,
                    "evidence_fragment_ids": action.evidence_fragment_ids,
                    "verified_at": action.verified_at,
                }
                for action in actions
            ],
        )

    async def get_report(
        self, session: AsyncSession, user_id: int, report_id: int
    ) -> ReviewReportResponse:
        report = await session.get(ReviewReport, report_id)
        if not report or report.user_id != user_id:
            raise AppError("REVIEW_NOT_FOUND", "复盘报告不存在", 404)
        return await self._to_response(session, report)

    async def list_reports(
        self, session: AsyncSession, user_id: int, limit: int = 50
    ) -> list[ReviewReportResponse]:
        reports = (
            await session.execute(
                select(ReviewReport)
                .where(ReviewReport.user_id == user_id)
                .order_by(ReviewReport.id.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [await self._to_response(session, report) for report in reports]

    async def add_feedback(
        self,
        session: AsyncSession,
        user_id: int,
        item_id: int,
        request: ReviewFeedbackRequest,
    ) -> ReviewItemResponse:
        item = await session.get(ReviewItem, item_id)
        if not item or item.user_id != user_id:
            raise AppError("REVIEW_ITEM_NOT_FOUND", "复盘判断项不存在", 404)
        feedback: dict[str, Any] = {
            "decision": request.decision.value,
            "note": request.note,
        }
        item.feedback_json = feedback
        flag_modified(item, "feedback_json")
        await session.flush()
        return ReviewItemResponse(
            id=item.id,
            section=item.section,
            verdict=item.verdict,
            attribution=item.attribution,
            fragment_id=item.fragment_id,
            evidence_fragment_ids=item.evidence_fragment_ids,
            payload=item.payload_json,
            feedback=item.feedback_json,
        )


review_service = ReviewService()
