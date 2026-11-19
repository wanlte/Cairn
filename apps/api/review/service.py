from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from apps.api.analysis.service import analysis_service
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
from apps.api.profile.service import profile_service
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
from apps.api.samples.coverage import sample_coverage

PROMPT_VERSION = "review-v1"
_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "review" / "v1.txt"

PROFILE_GROUP_LABELS = {
    "identity_background": "身份与技术背景",
    "cognitive_style": "思考方式",
    "attention_trajectory": "关注方向",
    "high_frequency_pitfalls": "常见坑",
    "growth_signals": "成长信号",
}


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if hasattr(code, "value"):
        return str(code.value)
    if isinstance(exc, AppError):
        return exc.code
    return exc.__class__.__name__


_TECHNICAL_TEXT_RE = re.compile(
    r"period\s*=|outcome_status|evidence_fragment_ids|fragment_ids?\b", re.IGNORECASE
)


def _has_technical_text(value: Any) -> bool:
    return isinstance(value, str) and bool(_TECHNICAL_TEXT_RE.search(value))


def _friendly_text(value: Any) -> Any:
    """兜底清掉模型偶尔带进用户文案里的内部标识。"""
    if not isinstance(value, str) or not _has_technical_text(value):
        return value
    cleaned = re.sub(r"period\s*=\s*[^\s,，;；）)]+", "这一周期", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"outcome_status\s*=\s*[\w]+", "结果还没观察到", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"evidence_fragment_ids|fragment_ids?\b", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip(" ，,;；")


def _friendly_comparison(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    if _has_technical_text(value):
        return "这是第一段记录，暂时没有上一周期可以对比，后面多记几次就能看出变化。"
    return value.strip()


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
            **request.gateway_kwargs(),
        )

        coverage = await sample_coverage(session, user_id, list(fragments))
        desirability = await analysis_service.detect_desirability(
            session, user_id, list(fragments)
        )
        report = ReviewReport(
            user_id=user_id,
            period=request.period,
            status="RUNNING",
            overview_json={},
            coverage_json=coverage,
            prompt_version=PROMPT_VERSION,
            model=model,
            provider=provider.value if provider else None,
            idempotency_key=request.idempotency_key,
        )
        session.add(report)
        await session.flush()

        profile_context: list[dict[str, str]] = []
        try:
            profile = await profile_service.get_current(session, user_id)
        except AppError:
            profile = None
        if profile:
            for claim in profile.claims:
                group = getattr(claim.group, "value", str(claim.group))
                profile_context.append(
                    {
                        "方面": PROFILE_GROUP_LABELS.get(group, group),
                        "结论": claim.value,
                    }
                )

        settings = get_settings()
        fragment_payload = [
            {"id": item.id, "kind": item.kind, "payload": item.payload_json}
            for item in fragments
        ]
        user_payload: dict[str, Any] = {
            "period_label": "本次复盘",
            "fragments": fragment_payload,
        }
        if profile_context:
            user_payload["已有画像"] = profile_context
        user_payload["样本体检"] = coverage
        if desirability:
            user_payload["表达提醒"] = [
                {"fragment_id": item.fragment_id, "痕迹": item.signals}
                for item in desirability
            ]
        if request.direction:
            user_payload["direction"] = request.direction
        if request.supplement:
            user_payload["supplement"] = request.supplement
        gateway_request = GatewayRequest(
            task="review",
            messages=[
                {"role": "system", "content": _load_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
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
        judgment_records: list[ReviewItem] = []
        for item in output.judgments:
            record = ReviewItem(
                user_id=user_id,
                report_id=report.id,
                section="judgment",
                fragment_id=item.fragment_id,
                verdict=item.verdict.value,
                attribution=item.attribution.value,
                evidence_fragment_ids=item.evidence_fragment_ids,
                payload_json=item.model_dump(
                    mode="json",
                    exclude={"confidence", "reasoning_chain", "conflicts_with"},
                ),
                confidence_low=float(item.confidence.low) if item.confidence else None,
                confidence_high=float(item.confidence.high) if item.confidence else None,
                reasoning_chain_json=item.reasoning_chain,
                conflict_with_json=[],
            )
            session.add(record)
            judgment_records.append(record)
        await session.flush()
        for item, record in zip(output.judgments, judgment_records, strict=True):
            conflicts = [
                judgment_records[index].id
                for index in item.conflicts_with
                if 0 <= index < len(judgment_records)
            ]
            if conflicts:
                record.conflict_with_json = conflicts
                flag_modified(record, "conflict_with_json")
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
        overview = dict(report.overview_json or {})
        if "comparison_with_last_period" in overview:
            overview["comparison_with_last_period"] = _friendly_comparison(
                overview.get("comparison_with_last_period")
            )
        return ReviewReportResponse(
            id=report.id,
            user_id=report.user_id,
            period=report.period,
            status=report.status,
            overview=overview,
            coverage=report.coverage_json or {},
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
                    payload={
                        key: _friendly_text(value)
                        for key, value in (item.payload_json or {}).items()
                    },
                    feedback=item.feedback_json,
                    confidence_low=(
                        float(item.confidence_low) if item.confidence_low is not None else None
                    ),
                    confidence_high=(
                        float(item.confidence_high) if item.confidence_high is not None else None
                    ),
                    reasoning_chain=item.reasoning_chain_json or [],
                    conflicts_with=item.conflict_with_json or [],
                    appeal_status=item.appeal_status,
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
            payload={
                key: _friendly_text(value)
                for key, value in (item.payload_json or {}).items()
            },
            feedback=item.feedback_json,
            confidence_low=float(item.confidence_low) if item.confidence_low is not None else None,
            confidence_high=float(item.confidence_high) if item.confidence_high is not None else None,
            reasoning_chain=item.reasoning_chain_json or [],
            conflicts_with=item.conflict_with_json or [],
            appeal_status=item.appeal_status,
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
        """导出面向用户的复盘记录：只保留结论，不暴露任何技术字段。"""
        report = await self.get_report(session, user_id, report_id)
        verdict_labels = {
            "CORRECT": "判断对了",
            "PARTIAL": "有对有偏",
            "WRONG": "这次看偏了",
            "UNVERIFIED": "还待验证",
        }
        attribution_labels = {
            "NONE": "没有特别的原因",
            "KNOWLEDGE_GAP": "当时还缺这块知识",
            "VERIFICATION_MISSING": "少了验证这一步",
            "ASSUMPTION_WRONG": "前提假设不成立",
            "TIME_PRESSURE": "时间太赶",
            "COMMUNICATION": "沟通没对齐",
        }
        when = report.created_at.strftime("%Y 年 %m 月 %d 日") if report.created_at else ""
        lines = ["# 我的复盘记录", ""]
        if when:
            lines.extend([f"记于 {when}", ""])

        overview = report.overview or {}
        dialogue_count = overview.get("dialogue_count")
        comparison = overview.get("comparison_with_last_period")
        domains = overview.get("domain_distribution") or []
        topics = overview.get("investment_distribution") or []

        lines.extend(["## 这一段做了什么", ""])
        stat_count = 0
        if isinstance(dialogue_count, int) and dialogue_count > 0:
            lines.append(f"- 一共回看了 {dialogue_count} 段对话")
            stat_count += 1
        for entry in domains[:5]:
            if isinstance(entry, dict) and entry.get("domain"):
                lines.append(f"- {entry['domain']}：{entry.get('count', 0)} 段")
                stat_count += 1
        for entry in topics[:5]:
            if isinstance(entry, dict) and entry.get("topic"):
                lines.append(f"- 在「{entry['topic']}」上花了 {entry.get('count', 0)} 次讨论")
                stat_count += 1
        if isinstance(comparison, str) and comparison.strip():
            lines.append(f"- {comparison.strip()}")
            stat_count += 1
        if stat_count == 0:
            lines.append("- 这次还没有可用的统计")
        lines.append("")

        lines.extend(["## 值得回看的几件事", ""])
        key_events = [item for item in report.items if item.section == "key_event"]
        for item in key_events:
            payload = item.payload or {}
            background = payload.get("background", "")
            judgment = payload.get("my_judgment", "")
            outcome = payload.get("actual_outcome", "")
            if background:
                lines.append(f"### {background}")
                if judgment:
                    lines.append(f"- 当时的判断：{judgment}")
                if outcome:
                    lines.append(f"- 后来怎么样：{outcome}")
                lines.append("")
        if not key_events:
            lines.extend(["这次没有特别标出来的事件。", ""])

        lines.extend(["## 判断与原因", ""])
        judgments = [item for item in report.items if item.section == "judgment"]
        for item in judgments:
            verdict = verdict_labels.get(item.verdict or "", "还待验证")
            attribution = attribution_labels.get(item.attribution or "", "")
            reason = (item.payload or {}).get("reason", "")
            suffix = f"（{attribution}）" if attribution else ""
            lines.append(f"- **{verdict}**{suffix}：{reason}")
        if not judgments:
            lines.append("- 这次没有需要复核的判断。")
        lines.append("")

        lines.extend(["## 想法的转变", ""])
        changes = [item for item in report.items if item.section == "cognitive_change"]
        for item in changes:
            payload = item.payload or {}
            old = payload.get("old_belief", "")
            new = payload.get("new_belief", "")
            if old or new:
                lines.append(f"- 从「{old}」，到现在更倾向「{new}」")
        if not changes:
            lines.append("- 这次没有记录到明显的想法变化。")
        lines.append("")

        lines.extend(["## 接下来做什么", ""])
        for action in report.action_items:
            checked = "x" if action.status == ActionItemStatus.VERIFIED else " "
            lines.append(f"- [{checked}] {action.content}")
            if action.verification:
                lines.append(f"  - 怎么算做到：{action.verification}")
            if action.verification_note:
                lines.append(f"  - 我的记录：{action.verification_note}")
        if not report.action_items:
            lines.append("- 这次没有定下行动项。")
        return "\n".join(lines) + "\n"


review_service = ReviewService()
