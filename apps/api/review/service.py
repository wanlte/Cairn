from __future__ import annotations

import json
from datetime import UTC, datetime
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
    ActionItemResponse,
    ActionItemStatus,
    ActionItemVerifyRequest,
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

    @staticmethod
    def _action_to_response(
        action: ActionItem, report: ReviewReport | None = None
    ) -> ActionItemResponse:
        return ActionItemResponse(
            id=action.id,
            report_id=action.report_id,
            period=report.period if report else None,
            content=action.content,
            verification=action.verification,
            status=ActionItemStatus(action.status or "PENDING"),
            verification_note=action.verification_note,
            evidence_fragment_ids=action.evidence_fragment_ids,
            verified_at=action.verified_at,
        )

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
                self._action_to_response(action, report) for action in actions
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

    async def list_action_items(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        status: ActionItemStatus | None = None,
        limit: int = 100,
    ) -> list[ActionItemResponse]:
        stmt = select(ActionItem, ReviewReport).join(
            ReviewReport, ActionItem.report_id == ReviewReport.id
        )
        stmt = stmt.where(ActionItem.user_id == user_id)
        if status:
            stmt = stmt.where(ActionItem.status == status.value)
        rows = (
            await session.execute(
                stmt.order_by(ActionItem.id.desc()).limit(limit)
            )
        ).all()
        return [self._action_to_response(action, report) for action, report in rows]

    async def _set_action_status(
        self,
        session: AsyncSession,
        user_id: int,
        action_id: int,
        *,
        status: ActionItemStatus,
        request: ActionItemVerifyRequest,
    ) -> ActionItemResponse:
        action = await session.get(ActionItem, action_id)
        if not action or action.user_id != user_id:
            raise AppError("ACTION_ITEM_NOT_FOUND", "行动项不存在", 404)
        action.status = status.value
        action.verification_note = request.note
        action.verified_at = (
            datetime.now(UTC) if status == ActionItemStatus.VERIFIED else None
        )
        await session.flush()
        report = await session.get(ReviewReport, action.report_id)
        return self._action_to_response(action, report)

    async def verify_action_item(
        self,
        session: AsyncSession,
        user_id: int,
        action_id: int,
        request: ActionItemVerifyRequest,
    ) -> ActionItemResponse:
        return await self._set_action_status(
            session,
            user_id,
            action_id,
            status=ActionItemStatus.VERIFIED,
            request=request,
        )

    async def reopen_action_item(
        self,
        session: AsyncSession,
        user_id: int,
        action_id: int,
        request: ActionItemVerifyRequest,
    ) -> ActionItemResponse:
        return await self._set_action_status(
            session,
            user_id,
            action_id,
            status=ActionItemStatus.REOPENED,
            request=request,
        )

    async def export_report_markdown(
        self, session: AsyncSession, user_id: int, report_id: int
    ) -> str:
        report = await self.get_report(session, user_id, report_id)
        lines = [
            f"# Cairn 周复盘 · {report.period}",
            "",
            f"模型：{report.provider or '-'} / {report.model or '-'}",
            f"提示词版本：{report.prompt_version}",
            "",
            "## 概览",
            json.dumps(report.overview, ensure_ascii=False, indent=2),
            "",
            "## 关键事件",
        ]
        for item in report.items:
            if item.section != "key_event":
                continue
            lines.append(
                f"- #{item.fragment_id} {item.payload.get('background', '')}"
            )
        lines.extend(["", "## 对错判断"])
        for item in report.items:
            if item.section != "judgment":
                continue
            evidence = ", ".join(str(value) for value in item.evidence_fragment_ids)
            lines.append(
                f"- **{item.verdict}** · {item.attribution or '-'} · "
                f"{item.payload.get('reason', '')}（证据 #{evidence}）"
            )
        lines.extend(["", "## 认知变化"])
        for item in report.items:
            if item.section != "cognitive_change":
                continue
            lines.append(
                f"- {item.payload.get('old_belief', '')} → {item.payload.get('new_belief', '')}"
            )
        lines.extend(["", "## 行动项"])
        for action in report.action_items:
            lines.append(
                f"- [{ 'x' if action.status == ActionItemStatus.VERIFIED else ' ' }] "
                f"{action.content}｜验证：{action.verification}"
            )
            if action.verification_note:
                lines.append(f"  - 验证备注：{action.verification_note}")
        return "\n".join(lines) + "\n"


review_service = ReviewService()
