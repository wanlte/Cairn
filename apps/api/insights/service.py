from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models.extraction import Fragment
from apps.api.db.models.profile import ProfileClaim, ProfileSnapshot
from apps.api.db.models.relation import RelationEdge
from apps.api.db.models.review import ReviewReport
from apps.api.db.models.sample import CounterfactualEntry
from apps.api.insights.schemas import (
    DriftClaim,
    DriftCurveResponse,
    DriftPoint,
    GraphEdge,
    GraphNode,
    GraphResponse,
)

_TOPIC_KEYS = ("domain", "category", "topic")
_PERSON_KEYS = ("sender", "source_label", "who")


def _labels(payload: dict[str, Any] | None) -> list[str]:
    if not payload:
        return []
    return [
        str(payload[key]).strip()[:32]
        for key in _TOPIC_KEYS
        if isinstance(payload.get(key), str) and payload[key].strip()
    ]


def _person(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    for key in _PERSON_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:32]
    return None


class InsightsService:
    async def drift_curve(
        self,
        session: AsyncSession,
        user_id: int,
        group: str | None = None,
    ) -> DriftCurveResponse:
        snapshots = (
            await session.execute(
                select(ProfileSnapshot)
                .where(ProfileSnapshot.user_id == user_id)
                .order_by(ProfileSnapshot.id)
            )
        ).scalars().all()
        reviews = (
            await session.execute(
                select(func.count())
                .select_from(ReviewReport)
                .where(ReviewReport.user_id == user_id)
            )
        ).scalar_one()
        counterfactuals = (
            await session.execute(
                select(func.count())
                .select_from(CounterfactualEntry)
                .where(CounterfactualEntry.user_id == user_id)
            )
        ).scalar_one()

        points: list[DriftPoint] = []
        for index, snapshot in enumerate(snapshots):
            stmt = select(ProfileClaim).where(
                ProfileClaim.snapshot_id == snapshot.id,
                ProfileClaim.is_deleted.is_(False),
            )
            if group:
                stmt = stmt.where(ProfileClaim.group_name == group)
            claims = (await session.execute(stmt.order_by(ProfileClaim.id))).scalars().all()
            points.append(
                DriftPoint(
                    snapshot_id=snapshot.id,
                    period=snapshot.period,
                    created_at=snapshot.created_at,
                    claims=[
                        DriftClaim(
                            key=claim.claim_key,
                            value=claim.value_text,
                            group=claim.group_name,
                        )
                        for claim in claims
                    ],
                    triggers={
                        "复盘": reviews if index == len(snapshots) - 1 else 0,
                        "补录": counterfactuals if index == len(snapshots) - 1 else 0,
                    },
                )
            )
        return DriftCurveResponse(points=points, total_snapshots=len(points))

    async def rebuild_graph(self, session: AsyncSession, user_id: int) -> int:
        fragments = (
            await session.execute(
                select(Fragment).where(Fragment.user_id == user_id)
            )
        ).scalars().all()
        pairs: dict[tuple[str, str, str], float] = defaultdict(float)

        for fragment in fragments:
            topics = sorted(set(_labels(fragment.payload_json)))
            speaker = _person(fragment.payload_json)
            for i, first in enumerate(topics):
                for second in topics[i + 1 :]:
                    pairs[(first, second, "topic")] += 1
                if speaker and speaker != first:
                    pairs[(speaker, first, "person_topic")] += 1

        sources = (
            await session.execute(
                select(CounterfactualEntry.source_label).where(
                    CounterfactualEntry.user_id == user_id,
                    CounterfactualEntry.source_label.is_not(None),
                )
            )
        ).scalars().all()
        persons = sorted({value.strip()[:32] for value in sources if value.strip()})
        for i, first in enumerate(persons):
            for second in persons[i + 1 :]:
                pairs[(first, second, "person")] += 1

        existing = {
            (row.source_label, row.target_label, row.kind): row
            for row in (
                await session.execute(
                    select(RelationEdge).where(RelationEdge.user_id == user_id)
                )
            ).scalars().all()
        }
        for (source, target, kind), weight in pairs.items():
            key = (source, target, kind)
            if key in existing:
                existing[key].weight = weight
            else:
                session.add(
                    RelationEdge(
                        user_id=user_id,
                        source_label=source,
                        target_label=target,
                        kind=kind,
                        weight=weight,
                    )
                )
        await session.flush()
        return len(pairs)

    async def graph(self, session: AsyncSession, user_id: int) -> GraphResponse:
        rows = (
            await session.execute(
                select(RelationEdge).where(RelationEdge.user_id == user_id)
            )
        ).scalars().all()
        weights: dict[str, float] = defaultdict(float)
        kinds: dict[str, str] = {}
        edges: list[GraphEdge] = []
        for row in rows:
            edges.append(
                GraphEdge(
                    source=row.source_label,
                    target=row.target_label,
                    kind=row.kind,
                    weight=float(row.weight),
                )
            )
            for label in (row.source_label, row.target_label):
                weights[label] += float(row.weight)
                if (
                    row.kind in {"person", "person_topic"}
                    and label == row.source_label
                ):
                    kinds[label] = "person"
                kinds.setdefault(label, "topic")

        nodes = [
            GraphNode(
                id=label,
                label=label,
                kind=kinds.get(label, "topic"),
                weight=round(weight, 2),
            )
            for label, weight in sorted(weights.items(), key=lambda item: -item[1])
        ]
        return GraphResponse(nodes=nodes, edges=edges)


insights_service = InsightsService()
