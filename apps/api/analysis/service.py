from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from apps.api.db.models.analysis import AnalysisAppeal, DesirabilityFlag
from apps.api.db.models.extraction import Fragment
from apps.api.db.models.review import ReviewItem
from apps.api.errors import AppError
from apps.api.review.schemas import (
    AppealResponse,
    DesirabilityFlagResponse,
    EvidenceChainResponse,
    EvidenceStep,
)

_SOCIAL_PATTERNS: tuple[tuple[str, float], ...] = (
    ("其实我更想", 0.45),
    ("说出来有点", 0.4),
    ("大家都觉得", 0.4),
    ("别人都说", 0.4),
    ("按理说", 0.35),
    ("照理", 0.35),
    ("正常来说", 0.3),
    ("理性上", 0.3),
    ("应该", 0.2),
    ("不得不", 0.2),
    ("情绪上", 0.2),
    ("必须", 0.15),
)


def _text_of(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    return " ".join(str(value) for value in payload.values() if isinstance(value, str))


def _score_signals(text: str) -> tuple[float, list[str]]:
    hits = [(word, weight) for word, weight in _SOCIAL_PATTERNS if word in text]
    if not hits:
        return 0.0, []
    return round(min(1.0, sum(weight for _, weight in hits)), 2), [word for word, _ in hits]


class AnalysisService:
    async def detect_desirability(
        self,
        session: AsyncSession,
        user_id: int,
        fragments: list[Fragment],
    ) -> list[DesirabilityFlagResponse]:
        """标记那些更像‘应该怎么说’而不是‘真实怎么想’的记录。"""
        results: list[DesirabilityFlagResponse] = []
        for fragment in fragments:
            score, signals = _score_signals(_text_of(fragment.payload_json))
            if not signals:
                continue
            existing = (
                await session.execute(
                    select(DesirabilityFlag).where(
                        DesirabilityFlag.user_id == user_id,
                        DesirabilityFlag.fragment_id == fragment.id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.score = score
                existing.signals_json = signals
                flag_modified(existing, "signals_json")
            else:
                existing = DesirabilityFlag(
                    user_id=user_id,
                    fragment_id=fragment.id,
                    score=score,
                    signals_json=signals,
                )
                session.add(existing)
            results.append(
                DesirabilityFlagResponse(
                    fragment_id=fragment.id,
                    score=score,
                    signals=signals,
                    summary=f"这条记录里有 {len(signals)} 处‘应该怎么说’的痕迹，可以再想想真实想法。",
                )
            )
        await session.flush()
        return results

    async def list_desirability(
        self, session: AsyncSession, user_id: int
    ) -> list[DesirabilityFlagResponse]:
        rows = (
            await session.execute(
                select(DesirabilityFlag)
                .where(DesirabilityFlag.user_id == user_id)
                .order_by(DesirabilityFlag.score.desc())
            )
        ).scalars().all()
        return [
            DesirabilityFlagResponse(
                fragment_id=row.fragment_id,
                score=float(row.score),
                signals=row.signals_json or [],
                summary=f"这条记录里有 {len(row.signals_json or [])} 处‘应该怎么说’的痕迹。",
            )
            for row in rows
        ]

    async def submit_appeal(
        self,
        session: AsyncSession,
        user_id: int,
        item_id: int,
        reason: str,
    ) -> AppealResponse:
        item = await session.get(ReviewItem, item_id)
        if not item or item.user_id != user_id:
            raise AppError("REVIEW_ITEM_NOT_FOUND", "这条结论不存在", 404, retryable=False)
        existing = (
            await session.execute(
                select(AnalysisAppeal).where(AnalysisAppeal.item_id == item_id)
            )
        ).scalar_one_or_none()
        if existing and existing.status == "PENDING":
            raise AppError("APPEAL_PENDING", "这条结论已经在复核中", 409, retryable=False)
        if existing:
            existing.reason = reason.strip()
            existing.status = "PENDING"
            existing.resolution_note = None
            existing.resolved_at = None
        else:
            existing = AnalysisAppeal(
                user_id=user_id,
                item_id=item_id,
                reason=reason.strip(),
                status="PENDING",
            )
            session.add(existing)
        item.appeal_status = "PENDING"
        await session.flush()
        return self._appeal_response(existing)

    async def list_appeals(
        self, session: AsyncSession, user_id: int, status: str | None = None
    ) -> list[AppealResponse]:
        stmt = select(AnalysisAppeal).where(AnalysisAppeal.user_id == user_id)
        if status:
            stmt = stmt.where(AnalysisAppeal.status == status)
        rows = (
            await session.execute(stmt.order_by(AnalysisAppeal.created_at.desc()))
        ).scalars().all()
        return [self._appeal_response(row) for row in rows]

    async def resolve_appeal(
        self,
        session: AsyncSession,
        user_id: int,
        appeal_id: int,
        decision: str,
        note: str | None,
    ) -> AppealResponse:
        appeal = await session.get(AnalysisAppeal, appeal_id)
        if not appeal or appeal.user_id != user_id:
            raise AppError("APPEAL_NOT_FOUND", "找不到这次申诉", 404, retryable=False)
        appeal.status = decision
        appeal.resolution_note = note
        appeal.resolved_at = datetime.now(UTC)
        item = await session.get(ReviewItem, appeal.item_id)
        if item:
            item.appeal_status = decision
        await session.flush()
        return self._appeal_response(appeal)

    @staticmethod
    def _appeal_response(appeal: AnalysisAppeal) -> AppealResponse:
        return AppealResponse(
            id=appeal.id,
            item_id=appeal.item_id,
            reason=appeal.reason,
            status=appeal.status,
            resolution_note=appeal.resolution_note,
            created_at=appeal.created_at,
            resolved_at=appeal.resolved_at,
        )

    async def evidence_chain(
        self, session: AsyncSession, user_id: int, item_id: int
    ) -> EvidenceChainResponse:
        item = await session.get(ReviewItem, item_id)
        if not item or item.user_id != user_id:
            raise AppError("REVIEW_ITEM_NOT_FOUND", "这条结论不存在", 404, retryable=False)
        evidence: list[EvidenceStep] = []
        if item.evidence_fragment_ids:
            rows = (
                await session.execute(
                    select(Fragment).where(
                        Fragment.user_id == user_id,
                        Fragment.id.in_(item.evidence_fragment_ids),
                    )
                )
            ).scalars().all()
            evidence = [
                EvidenceStep(
                    fragment_id=row.id,
                    kind=row.kind,
                    payload=row.payload_json or {},
                )
                for row in rows
            ]
        payload = item.payload_json or {}
        conclusion = str(
            payload.get("reason")
            or payload.get("my_judgment")
            or payload.get("new_belief")
            or item.verdict
            or item.section
        )
        return EvidenceChainResponse(
            item_id=item.id,
            section=item.section,
            conclusion=conclusion,
            reasoning_chain=item.reasoning_chain_json or [],
            confidence_low=float(item.confidence_low) if item.confidence_low is not None else None,
            confidence_high=float(item.confidence_high) if item.confidence_high is not None else None,
            conflicts_with=item.conflict_with_json or [],
            appeal_status=item.appeal_status,
            evidence=evidence,
        )


analysis_service = AnalysisService()
