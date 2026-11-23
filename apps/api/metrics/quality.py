from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models.analysis import AnalysisAppeal
from apps.api.db.models.profile import ProfileClaim, ProfileSnapshot
from apps.api.db.models.review import ReviewItem, ReviewReport
from apps.api.gateway.metering import LlmCallLog
from apps.api.metrics.schemas import MetricPair, QualityMetrics


def _rate(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


async def quality_metrics(
    session: AsyncSession, user_id: int, since: datetime
) -> QualityMetrics:
    calls = (
        await session.execute(
            select(LlmCallLog).where(
                LlmCallLog.user_id == user_id,
                LlmCallLog.created_at >= since,
            )
        )
    ).scalars().all()
    schema_total = [c for c in calls if c.task_type in {"review", "profile", "plan", "extract"}]
    schema_pass = [c for c in schema_total if c.status == "ok"]

    items = (
        await session.execute(
            select(ReviewItem).where(
                ReviewItem.user_id == user_id,
                ReviewItem.created_at >= since,
            )
        )
    ).scalars().all()
    evidence_hit = sum(
        1
        for item in items
        if item.fragment_id is not None or (item.evidence_fragment_ids or [])
    )
    appeals = (
        await session.execute(
            select(AnalysisAppeal).where(
                AnalysisAppeal.user_id == user_id,
                AnalysisAppeal.created_at >= since,
            )
        )
    ).scalars().all()
    accepted = sum(1 for a in appeals if a.status == "ACCEPTED")
    appealed_items = sum(1 for item in items if item.appeal_status != "NONE")

    snapshots = (
        await session.execute(
            select(ProfileSnapshot)
            .where(
                ProfileSnapshot.user_id == user_id,
                ProfileSnapshot.created_at >= since,
            )
            .order_by(ProfileSnapshot.id)
        )
    ).scalars().all()
    stability = await _stability(session, snapshots)

    reports = (
        await session.execute(
            select(ReviewReport).where(
                ReviewReport.user_id == user_id,
                ReviewReport.created_at >= since,
            )
        )
    ).scalars().all()
    coverages = [
        float((r.coverage_json or {}).get("score") or 0)
        for r in reports
    ]
    coverage_avg = round(sum(coverages) / len(coverages), 2) if coverages else 0.0
    buckets: dict[str, int] = {}
    for score in coverages:
        level = "较高" if score >= 70 else "中等" if score >= 40 else "较低"
        buckets[level] = buckets.get(level, 0) + 1
    distribution = [{"level": k, "count": v} for k, v in buckets.items()]

    confidence_values = [
        float(item.confidence_high)
        for item in items
        if item.confidence_high is not None
    ]
    confidence_avg = (
        round(sum(confidence_values) / len(confidence_values), 4)
        if confidence_values
        else 0.0
    )

    return QualityMetrics(
        schema_pass_rate=_rate(len(schema_pass), len(schema_total)),
        evidence_hit_rate=_rate(evidence_hit, len(items)),
        profile_stability=stability,
        appeal_rate=_rate(appealed_items, len(items)),
        appeal_correction_rate=_rate(accepted, len(appeals)),
        confidence_avg=confidence_avg,
        coverage_avg=coverage_avg,
        coverage_distribution=distribution,
        speed_accuracy=await _speed_accuracy(session, user_id, since, calls, items),
    )


async def _stability(
    session: AsyncSession, snapshots: list[ProfileSnapshot]
) -> float:
    if len(snapshots) < 2:
        return 1.0
    scores: list[float] = []
    for previous, current in pairwise(snapshots):
        old_claims = (
            await session.execute(
                select(ProfileClaim).where(ProfileClaim.snapshot_id == previous.id)
            )
        ).scalars().all()
        new_claims = (
            await session.execute(
                select(ProfileClaim).where(ProfileClaim.snapshot_id == current.id)
            )
        ).scalars().all()
        old_keys = {c.claim_key for c in old_claims}
        new_keys = {c.claim_key for c in new_claims}
        if not old_keys:
            scores.append(0.0)
            continue
        retained = len(old_keys & new_keys) / len(old_keys)
        scores.append(round(retained, 4))
    return round(sum(scores) / len(scores), 4) if scores else 1.0


async def _speed_accuracy(
    session: AsyncSession,
    user_id: int,
    since: datetime,
    calls: list[LlmCallLog],
    items: list[ReviewItem],
) -> list[MetricPair]:
    by_model: dict[str, list[int]] = {}
    for call in calls:
        if call.task_type != "review" or call.latency_ms is None:
            continue
        model = call.model or "unknown"
        by_model.setdefault(model, []).append(call.latency_ms)

    reports = (
        await session.execute(
            select(ReviewReport).where(
                ReviewReport.user_id == user_id,
                ReviewReport.created_at >= since,
            )
        )
    ).scalars().all()
    report_models = {r.id: (r.model or "unknown") for r in reports}
    item_hits: dict[str, list[int]] = {}
    for item in items:
        model = report_models.get(item.report_id, "unknown")
        hit = 1 if item.fragment_id is not None or (item.evidence_fragment_ids or []) else 0
        item_hits.setdefault(model, []).append(hit)

    result: list[MetricPair] = []
    for model, latencies in by_model.items():
        avg_latency = sum(latencies) / len(latencies)
        hits = item_hits.get(model, [])
        accuracy = (sum(hits) / len(hits)) if hits else 0.0
        result.append(
            MetricPair(
                label=model,
                fast=round(avg_latency / 1000, 2),
                accurate=round(accuracy, 4),
                sample=len(latencies),
            )
        )
    return sorted(result, key=lambda x: x.sample, reverse=True)[:8]


def window_start(days: int) -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
