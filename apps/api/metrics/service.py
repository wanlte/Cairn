from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models.metrics import UserEvent
from apps.api.db.models.planning import WeeklyFill
from apps.api.db.models.platform import ApiKey, AuditLog, ConsentRecord
from apps.api.db.models.review import ReviewReport
from apps.api.db.models.workspace import WorkspaceTask, WorkspaceTaskEvent
from apps.api.gateway.metering import LlmCallLog
from apps.api.metrics.quality import quality_metrics, window_start
from apps.api.metrics.schemas import (
    BehaviorMetrics,
    CostMetrics,
    EventResponse,
    FunnelStep,
    MetricPoint,
    MetricsOverview,
    SecurityMetrics,
    SystemMetrics,
    ValueMetrics,
)


def _rate(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[index]


class MetricsService:
    async def overview(
        self, session: AsyncSession, user_id: int, window_days: int = 30
    ) -> MetricsOverview:
        since = window_start(window_days)
        system = await self._system(session, user_id, since)
        quality = await quality_metrics(session, user_id, since)
        cost = await self._cost(session, user_id, since)
        behavior = await self._behavior(session, user_id, since)
        value = await self._value(session, user_id, since)
        security = await self._security(session, user_id, since)
        return MetricsOverview(
            window_days=window_days,
            generated_at=datetime.now(UTC).replace(tzinfo=None),
            system=system,
            quality=quality,
            cost=cost,
            behavior=behavior,
            value=value,
            security=security,
            headline={
                "latency_p95_ms": system.latency_p95_ms,
                "evidence_hit_rate": quality.evidence_hit_rate,
                "total_cost_cny": cost.total_cost_cny,
                "active_users_steps": len(behavior.funnel),
            },
        )

    async def _system(
        self, session: AsyncSession, user_id: int, since: datetime
    ) -> SystemMetrics:
        tasks = (
            await session.execute(
                select(WorkspaceTask).where(
                    WorkspaceTask.user_id == user_id,
                    WorkspaceTask.created_at >= since,
                )
            )
        ).scalars().all()
        done = sum(1 for t in tasks if t.status == "DONE")
        calls = (
            await session.execute(
                select(LlmCallLog).where(
                    LlmCallLog.user_id == user_id,
                    LlmCallLog.created_at >= since,
                )
            )
        ).scalars().all()
        latencies = [c.latency_ms for c in calls if c.latency_ms is not None]
        tasks_latency = [
            int((t.finished_at - t.created_at).total_seconds() * 1000)
            for t in tasks
            if t.finished_at and t.created_at
        ]
        all_latency = latencies + tasks_latency
        events = (
            await session.execute(
                select(WorkspaceTaskEvent).where(
                    WorkspaceTaskEvent.created_at >= since,
                    WorkspaceTaskEvent.task_id.in_([t.id for t in tasks]) if tasks else False,
                )
            )
        ).scalars().all()
        stage_map: dict[str, list[int]] = {}
        for event in events:
            stage = event.stage or "RUNNING"
            stage_map.setdefault(stage, 0)
            stage_map[stage] += 1
        error_codes: dict[str, int] = {}
        for call in calls:
            if call.error_code:
                error_codes[call.error_code] = error_codes.get(call.error_code, 0) + 1
        daily: dict[str, list[int]] = {}
        for call in calls:
            if call.latency_ms is None:
                continue
            bucket = call.created_at.strftime("%Y-%m-%d")
            daily.setdefault(bucket, []).append(call.latency_ms)
        trend = [
            MetricPoint(bucket=k, value=round(sum(v) / len(v), 1))
            for k, v in sorted(daily.items())
        ]
        return SystemMetrics(
            total_requests=len(calls),
            success_rate=_rate(sum(1 for c in calls if c.status == "ok"), len(calls)),
            error_codes=[{"code": k, "count": v} for k, v in error_codes.items()],
            latency_p50_ms=_percentile(all_latency, 0.5),
            latency_p95_ms=_percentile(all_latency, 0.95),
            task_completion_rate=_rate(done, len(tasks)),
            stage_latency_ms=[{"stage": k, "count": v} for k, v in stage_map.items()],
            latency_trend=trend,
        )

    async def _cost(
        self, session: AsyncSession, user_id: int, since: datetime
    ) -> CostMetrics:
        calls = (
            await session.execute(
                select(LlmCallLog).where(
                    LlmCallLog.user_id == user_id,
                    LlmCallLog.created_at >= since,
                )
            )
        ).scalars().all()
        by_model: dict[str, dict] = {}
        daily: dict[str, float] = {}
        for call in calls:
            cost = float(call.cost_cny or 0)
            model = call.model or "unknown"
            item = by_model.setdefault(model, {"calls": 0, "cost": 0.0, "tokens": 0})
            item["calls"] += 1
            item["cost"] += cost
            item["tokens"] += (call.prompt_tokens or 0) + (call.completion_tokens or 0)
            bucket = call.created_at.strftime("%Y-%m-%d")
            daily[bucket] = daily.get(bucket, 0.0) + cost
        return CostMetrics(
            total_cost_cny=round(sum(float(c.cost_cny or 0) for c in calls), 6),
            total_calls=len(calls),
            total_tokens=sum((c.prompt_tokens or 0) + (c.completion_tokens or 0) for c in calls),
            retry_rate=_rate(sum(1 for c in calls if (c.retry_count or 0) > 0), len(calls)),
            fallback_rate=_rate(sum(1 for c in calls if c.fallback_from), len(calls)),
            failure_rate=_rate(sum(1 for c in calls if c.status == "failed"), len(calls)),
            by_model=[
                {"model": k, **{kk: round(vv, 6) if isinstance(vv, float) else vv for kk, vv in v.items()}}
                for k, v in by_model.items()
            ],
            cost_trend=[MetricPoint(bucket=k, value=round(v, 6)) for k, v in sorted(daily.items())],
        )

    async def _behavior(
        self, session: AsyncSession, user_id: int, since: datetime
    ) -> BehaviorMetrics:
        events = (
            await session.execute(
                select(UserEvent).where(
                    UserEvent.user_id == user_id,
                    UserEvent.created_at >= since,
                )
            )
        ).scalars().all()
        counts: dict[str, int] = {}
        for event in events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1
        funnel_keys = [
            "registered", "import_completed", "review_generated",
            "profile_generated", "returned",
        ]
        funnel = [FunnelStep(label=k, count=counts.get(k, 0)) for k in funnel_keys]
        feature_keys = [
            "review_generated", "profile_generated", "simulation_run",
            "decision_requested", "daily_answered", "plan_generated",
            "export_used", "pair_analysis",
        ]
        penetration = [
            {"feature": k, "count": counts.get(k, 0), "rate": _rate(counts.get(k, 0), len(events))}
            for k in feature_keys
        ]
        daily: dict[str, int] = {}
        for event in events:
            bucket = event.created_at.strftime("%Y-%m-%d")
            daily[bucket] = daily.get(bucket, 0) + 1
        return BehaviorMetrics(
            funnel=funnel,
            feature_penetration=penetration,
            events_by_day=[MetricPoint(bucket=k, value=float(v)) for k, v in sorted(daily.items())],
        )

    async def _value(
        self, session: AsyncSession, user_id: int, since: datetime
    ) -> ValueMetrics:
        reports = (
            await session.execute(
                select(ReviewReport).where(
                    ReviewReport.user_id == user_id,
                    ReviewReport.created_at >= since,
                )
            )
        ).scalars().all()
        scores = [float((r.coverage_json or {}).get("score") or 0) for r in reports]
        improvement = round(scores[-1] - scores[0], 2) if len(scores) >= 2 else 0.0
        fills = (
            await session.execute(
                select(WeeklyFill).where(
                    WeeklyFill.user_id == user_id,
                    WeeklyFill.created_at >= since,
                )
            )
        ).scalars().all()
        weeks = sorted({f.week for f in fills})
        streak = 0
        for week in reversed(weeks):
            if streak == 0 or self._is_next_week(weeks[-streak - 1], week):
                streak += 1
            else:
                break
        events = (
            await session.execute(
                select(UserEvent).where(
                    UserEvent.user_id == user_id,
                    UserEvent.created_at >= since,
                )
            )
        ).scalars().all()
        counts: dict[str, int] = {}
        for event in events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1
        return ValueMetrics(
            coverage_improvement=improvement,
            weekly_streak=streak,
            weekly_fills=len(fills),
            export_count=counts.get("export_used", 0),
            open_api_calls=counts.get("open_api_call", 0),
            pair_analysis_count=counts.get("pair_analysis", 0),
        )

    @staticmethod
    def _is_next_week(previous: str, current: str) -> bool:
        try:
            py, pw = int(previous[:4]), int(previous[-2:])
            cy, cw = int(current[:4]), int(current[-2:])
            return (cy == py and cw == pw + 1) or (cy == py + 1 and cw == 1 and pw >= 52)
        except (ValueError, IndexError):
            return False

    async def _security(
        self, session: AsyncSession, user_id: int, since: datetime
    ) -> SecurityMetrics:
        keys = (
            await session.execute(
                select(ApiKey).where(ApiKey.user_id == user_id)
            )
        ).scalars().all()
        audits = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.user_id == user_id,
                    AuditLog.created_at >= since,
                )
            )
        ).scalars().all()
        consents = (
            await session.execute(
                select(ConsentRecord).where(
                    ConsentRecord.user_id == user_id,
                    ConsentRecord.revoked_at.is_(None),
                )
            )
        ).scalars().all()
        denied = sum(1 for a in audits if "denied" in (a.action or "").lower())
        return SecurityMetrics(
            denied_requests=denied,
            revoked_keys=sum(1 for k in keys if k.revoked_at),
            consent_coverage=_rate(len(consents), max(len(keys), 1)),
            audit_events=len(audits),
            redaction_hits=0,
        )

    async def record_event(
        self,
        session: AsyncSession,
        user_id: int,
        event_type: str,
        payload: dict,
    ) -> EventResponse:
        event = UserEvent(user_id=user_id, event_type=event_type, payload_json=payload)
        session.add(event)
        await session.flush()
        return EventResponse(
            id=event.id,
            event_type=event.event_type,
            payload=event.payload_json,
            created_at=event.created_at,
        )


metrics_service = MetricsService()
