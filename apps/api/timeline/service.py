from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models.extraction import Fragment
from apps.api.db.models.ingestion import RawConversation, TurnPair
from apps.api.db.models.profile import ProfileSnapshot
from apps.api.db.models.review import ActionItem, ReviewReport
from apps.api.db.models.sample import CounterfactualEntry
from apps.api.timeline.schemas import TimelineEvent, TimelineEventType, TimelineResponse

_EVENT_FIELDS = ("what", "concept", "trait", "frustration", "summary", "evidence", "reason")


def _precision(value: str | None, *, has_time: bool) -> str:
    if not has_time or value not in {"HIGH", "LOW", "INFERRED"}:
        return "INFERRED"
    return value


def _summary_of(payload: dict[str, Any] | None, fallback: str) -> str:
    if not payload:
        return fallback
    for key in _EVENT_FIELDS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:200]
    return fallback


def _sort_key(event: TimelineEvent) -> tuple[int, float]:
    if event.occurred_at is None:
        return (0, 0.0)
    try:
        return (1, event.occurred_at.timestamp())
    except (ValueError, OSError, OverflowError):
        return (0, 0.0)


class TimelineService:
    async def build(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        event_types: list[TimelineEventType] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 200,
    ) -> TimelineResponse:
        wanted = set(event_types) if event_types else set(TimelineEventType)
        events: list[TimelineEvent] = []

        if TimelineEventType.CONVERSATION in wanted:
            rows = (
                await session.execute(
                    select(RawConversation).where(RawConversation.user_id == user_id)
                )
            ).scalars().all()
            for row in rows:
                precision = _precision(row.time_precision, has_time=bool(row.captured_at))
                events.append(
                    TimelineEvent(
                        id=f"conversation-{row.id}",
                        event_type=TimelineEventType.CONVERSATION,
                        occurred_at=row.captured_at or row.created_at,
                        time_precision=precision,
                        title=row.title or "对话记录",
                        summary=f"来源：{row.source_type}",
                        source_type=row.source_type,
                        ref_id=row.id,
                        low_confidence=precision != "HIGH",
                    )
                )

        if TimelineEventType.TURN in wanted:
            rows = (
                await session.execute(select(TurnPair).where(TurnPair.user_id == user_id))
            ).scalars().all()
            for row in rows:
                precision = _precision(row.time_precision, has_time=bool(row.asked_at))
                events.append(
                    TimelineEvent(
                        id=f"turn-{row.id}",
                        event_type=TimelineEventType.TURN,
                        occurred_at=row.asked_at or row.created_at,
                        time_precision=precision,
                        title="一段对话",
                        summary=(row.user_content or "")[:120],
                        ref_id=row.id,
                        low_confidence=precision != "HIGH",
                    )
                )

        if TimelineEventType.FRAGMENT in wanted:
            rows = (
                await session.execute(
                    select(Fragment, TurnPair)
                    .outerjoin(TurnPair, Fragment.turn_pair_id == TurnPair.id)
                    .where(Fragment.user_id == user_id)
                )
            ).all()
            for fragment, turn in rows:
                precision = _precision(
                    turn.time_precision if turn else None,
                    has_time=bool(turn and turn.asked_at),
                )
                events.append(
                    TimelineEvent(
                        id=f"fragment-{fragment.id}",
                        event_type=TimelineEventType.FRAGMENT,
                        occurred_at=(turn.asked_at if turn else None) or fragment.created_at,
                        time_precision=precision,
                        title="一条观察",
                        summary=_summary_of(fragment.payload_json, fragment.kind),
                        source_type=fragment.kind,
                        ref_id=fragment.id,
                        low_confidence=precision != "HIGH",
                    )
                )

        if TimelineEventType.COUNTERFACTUAL in wanted:
            rows = (
                await session.execute(
                    select(CounterfactualEntry).where(CounterfactualEntry.user_id == user_id)
                )
            ).scalars().all()
            for row in rows:
                events.append(
                    TimelineEvent(
                        id=f"counterfactual-{row.id}",
                        event_type=TimelineEventType.COUNTERFACTUAL,
                        occurred_at=row.created_at,
                        time_precision="HIGH",
                        title="反事实补录",
                        summary=(row.content or "")[:200],
                        source_type=row.prompt_type,
                        ref_id=row.id,
                    )
                )

        for event_type, model, title_prefix in (
            (TimelineEventType.REVIEW, ReviewReport, "复盘"),
            (TimelineEventType.PROFILE, ProfileSnapshot, "画像"),
        ):
            if event_type not in wanted:
                continue
            rows = (
                await session.execute(select(model).where(model.user_id == user_id))
            ).scalars().all()
            for row in rows:
                events.append(
                    TimelineEvent(
                        id=f"{event_type.value}-{row.id}",
                        event_type=event_type,
                        occurred_at=row.created_at,
                        time_precision="HIGH",
                        title=f"{title_prefix} · {row.period}",
                        summary=f"状态：{row.status}",
                        ref_id=row.id,
                    )
                )

        if TimelineEventType.ACTION in wanted:
            rows = (
                await session.execute(select(ActionItem).where(ActionItem.user_id == user_id))
            ).scalars().all()
            for row in rows:
                events.append(
                    TimelineEvent(
                        id=f"action-{row.id}",
                        event_type=TimelineEventType.ACTION,
                        occurred_at=row.verified_at or row.created_at,
                        time_precision="HIGH",
                        title="行动项",
                        summary=(row.content or "")[:200],
                        source_type=row.status,
                        ref_id=row.id,
                    )
                )

        def in_range(event: TimelineEvent) -> bool:
            if event.occurred_at is None:
                return date_from is None and date_to is None
            stamp = event.occurred_at.timestamp()
            if date_from and stamp < date_from.timestamp():
                return False
            return not (date_to and stamp > date_to.timestamp())

        filtered = [event for event in events if in_range(event)]
        filtered.sort(key=_sort_key, reverse=True)
        total = len(filtered)
        items = filtered[:limit]

        stamps = [
            event.occurred_at.timestamp()
            for event in items
            if event.occurred_at is not None
        ]
        span_days = round((max(stamps) - min(stamps)) / 86400, 1) if len(stamps) >= 2 else 0.0
        low_precision = sum(1 for event in items if event.time_precision != "HIGH")
        return TimelineResponse(
            items=items,
            total=total,
            span_days=span_days,
            low_precision_count=low_precision,
        )


timeline_service = TimelineService()
