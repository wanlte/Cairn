from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.db.models.extraction import Fragment
from apps.api.db.models.ingestion import RawConversation, TurnPair
from apps.api.db.models.profile import ProfileClaim, ProfileSnapshot
from apps.api.db.models.review import ReviewItem
from apps.api.gateway.factory import build_gateway_for_user
from apps.api.gateway.schemas import (
    GatewayErrorCode,
    GatewayOptions,
    GatewayRequest,
    UnifiedError,
)
from apps.api.retrieval.bm25 import BM25
from apps.api.retrieval.schemas import (
    RetrievalAskRequest,
    RetrievalAskResponse,
    RetrievalIndexRequest,
    RetrievalItemResponse,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)

RRF_K = 60
EMBED_BATCH = 32


def _normalize_vector(values: list[float], dim: int) -> list[float]:
    if len(values) > dim:
        return values[:dim]
    if len(values) < dim:
        return values + [0.0] * (dim - len(values))
    return values


def _fragment_text(fragment: Fragment) -> str:
    payload = fragment.payload_json or {}
    parts = [str(value) for value in payload.values() if isinstance(value, str)]
    return "\n".join(parts) or fragment.content_hash


def _domain(fragment: Fragment) -> str | None:
    payload = fragment.payload_json or {}
    return payload.get("domain") or payload.get("category")


async def _provider_for(
    session: AsyncSession,
    user_id: int,
    request: RetrievalIndexRequest | RetrievalSearchRequest,
):
    gateway, _credential_id, _model, _provider = await build_gateway_for_user(
        session,
        user_id,
        credential_id=request.credential_id,
        provider=request.provider,
        model=request.model,
    )
    if not gateway.providers:
        raise UnifiedError(
            GatewayErrorCode.SERVER_ERROR, "没有可用的 Provider", retryable=True
        )
    return gateway, gateway.providers[0]


class RetrievalService:
    async def index(
        self, session: AsyncSession, user_id: int, request: RetrievalIndexRequest
    ) -> dict:
        _gateway, provider = await _provider_for(session, user_id, request)
        fragments = (
            await session.execute(
                select(Fragment)
                .where(Fragment.user_id == user_id, Fragment.embedding.is_(None))
                .order_by(Fragment.id)
                .limit(request.limit)
            )
        ).scalars().all()
        if not fragments:
            return {"indexed": 0, "skipped": 0}

        indexed = 0
        settings = get_settings()
        for offset in range(0, len(fragments), EMBED_BATCH):
            batch = fragments[offset : offset + EMBED_BATCH]
            vectors = await provider.embed([_fragment_text(item) for item in batch])
            for fragment, vector in zip(batch, vectors, strict=True):
                fragment.embedding = _normalize_vector(vector, settings.embedding_dim)
                indexed += 1
        await session.flush()
        return {"indexed": indexed, "skipped": len(fragments) - indexed}

    async def _candidate_rows(self, session: AsyncSession, user_id: int) -> list[tuple[Fragment, str]]:
        rows = (
            await session.execute(
                select(Fragment, RawConversation.source_type)
                .join(TurnPair, Fragment.turn_pair_id == TurnPair.id)
                .join(RawConversation, TurnPair.conversation_id == RawConversation.id)
                .where(Fragment.user_id == user_id)
                .order_by(Fragment.id)
            )
        ).all()
        return [(row[0], row[1]) for row in rows]

    async def _verdict_map(self, session: AsyncSession, user_id: int) -> dict[int, str]:
        rows = (
            await session.execute(
                select(ReviewItem).where(
                    ReviewItem.user_id == user_id,
                    ReviewItem.section == "judgment",
                )
            )
        ).scalars().all()
        result: dict[int, str] = {}
        for item in rows:
            if not item.verdict:
                continue
            for fragment_id in item.evidence_fragment_ids or []:
                if item.verdict not in result.get(fragment_id, ""):
                    result[fragment_id] = item.verdict
        return result

    def _apply_filters(
        self,
        rows: list[tuple[Fragment, str]],
        scores: dict[int, float],
        filters,
        verdicts: dict[int, str],
    ) -> dict[int, float]:
        result: dict[int, float] = {}
        for fragment, platform in rows:
            fragment_id = fragment.id
            if fragment_id not in scores:
                continue
            if filters.from_date and fragment.created_at and fragment.created_at < filters.from_date:
                continue
            if filters.to_date and fragment.created_at and fragment.created_at > filters.to_date:
                continue
            if filters.domain and _domain(fragment) != filters.domain:
                continue
            if filters.platform and platform != filters.platform:
                continue
            if filters.verdict and verdicts.get(fragment_id) != filters.verdict.value:
                continue
            result[fragment_id] = scores[fragment_id]
        return result

    async def search(
        self, session: AsyncSession, user_id: int, request: RetrievalSearchRequest
    ) -> RetrievalSearchResponse:
        rows = await self._candidate_rows(session, user_id)
        if not rows:
            return RetrievalSearchResponse(
                query=request.query, items=[], used_vector=False, used_bm25=False, reranked=False
            )
        by_id = {fragment.id: (fragment, platform) for fragment, platform in rows}
        verdicts = await self._verdict_map(session, user_id)
        gateway = None

        bm25_scores: dict[int, float] = {}
        if request.enable_bm25:
            model = BM25()
            model.fit({fragment.id: _fragment_text(fragment) for fragment, _ in rows})
            bm25_scores = model.scores(request.query)

        vector_scores: dict[int, float] = {}
        used_vector = False
        if request.enable_vector and any(
            fragment.embedding is not None for fragment, _ in rows
        ):
            gateway, provider = await _provider_for(session, user_id, request)
            settings = get_settings()
            query_vector = _normalize_vector(
                (await provider.embed([request.query]))[0], settings.embedding_dim
            )
            vector_rows = (
                await session.execute(
                    select(Fragment.id, Fragment.embedding.cosine_distance(query_vector).label("distance"))
                    .where(
                        Fragment.user_id == user_id,
                        Fragment.embedding.is_not(None),
                    )
                    .order_by("distance")
                    .limit(request.candidate_k)
                )
            ).all()
            vector_scores = {
                row.id: max(0.0, 1.0 - float(row.distance)) for row in vector_rows
            }
            used_vector = True

        fused: dict[int, float] = defaultdict(float)
        for source_scores in (bm25_scores, vector_scores):
            ordered = sorted(source_scores.items(), key=lambda item: item[1], reverse=True)
            for rank, (fragment_id, _score) in enumerate(ordered[: request.candidate_k], start=1):
                fused[fragment_id] += 1.0 / (RRF_K + rank)

        fused = self._apply_filters(rows, fused, request.filters, verdicts)
        ordered_ids = sorted(fused, key=lambda item: fused[item], reverse=True)[
            : request.top_k
        ]

        items = [
            RetrievalItemResponse(
                fragment_id=fragment_id,
                kind=by_id[fragment_id][0].kind,
                score=round(fused[fragment_id], 6),
                bm25_score=round(bm25_scores.get(fragment_id, 0.0), 6),
                vector_score=round(vector_scores.get(fragment_id, 0.0), 6),
                payload=by_id[fragment_id][0].payload_json,
                domain=_domain(by_id[fragment_id][0]),
                platform=by_id[fragment_id][1],
                created_at=by_id[fragment_id][0].created_at,
            )
            for fragment_id in ordered_ids
        ]

        reranked = False
        if request.rerank and items:
            try:
                items = await self._rerank(session, user_id, request, items, gateway)
                reranked = True
            except Exception:  # noqa: BLE001 - rerank 失败保留原排序
                reranked = False

        return RetrievalSearchResponse(
            query=request.query,
            items=items,
            used_vector=used_vector,
            used_bm25=request.enable_bm25,
            reranked=reranked,
        )

    async def _rerank(
        self,
        session: AsyncSession,
        user_id: int,
        request: RetrievalSearchRequest,
        items: list[RetrievalItemResponse],
        gateway,
    ) -> list[RetrievalItemResponse]:
        if gateway is None:
            gateway, _provider = await _provider_for(session, user_id, request)
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["scores"],
            "properties": {
                "scores": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["fragment_id", "score"],
                        "properties": {
                            "fragment_id": {"type": "integer"},
                            "score": {"type": "number"},
                        },
                    },
                }
            },
        }
        candidates = [
            {"fragment_id": item.fragment_id, "payload": item.payload}
            for item in items
        ]
        response = await gateway.complete(
            GatewayRequest(
                task="rerank",
                messages=[
                    {
                        "role": "system",
                        "content": "按与查询的相关性给每个 fragment_id 打 0 到 1 的分数，只输出 JSON。",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"query": request.query, "candidates": candidates},
                            ensure_ascii=False,
                        ),
                    },
                ],
                options=GatewayOptions(
                    response_format="json_object",
                    output_schema=schema,
                ),
                user_id=user_id,
            )
        )
        scores = {
            int(row["fragment_id"]): float(row["score"])
            for row in (response.data or {}).get("scores", [])
            if "fragment_id" in row and "score" in row
        }
        for item in items:
            item.rerank_score = scores.get(item.fragment_id)
        return sorted(
            items,
            key=lambda item: item.rerank_score if item.rerank_score is not None else -1,
            reverse=True,
        )

    async def ask(
        self, session: AsyncSession, user_id: int, request: RetrievalAskRequest
    ) -> RetrievalAskResponse:
        search_result = await self.search(session, user_id, request)
        gateway, _provider = await _provider_for(session, user_id, request)

        profile_lines: list[str] = []
        if request.profile_aware:
            snapshot = (
                await session.execute(
                    select(ProfileSnapshot)
                    .where(ProfileSnapshot.user_id == user_id)
                    .order_by(ProfileSnapshot.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if snapshot:
                claims = (
                    await session.execute(
                        select(ProfileClaim).where(
                            ProfileClaim.snapshot_id == snapshot.id,
                            ProfileClaim.is_deleted.is_(False),
                        )
                    )
                ).scalars().all()
                profile_lines = [
                    f"[{claim.group_name}] {claim.claim_key}: {claim.value_text}"
                    for claim in claims[:20]
                ]

        context = {
            "query": request.query,
            "profile": profile_lines,
            "fragments": [
                {"fragment_id": item.fragment_id, "payload": item.payload}
                for item in search_result.items
            ],
        }
        response = await gateway.complete(
            GatewayRequest(
                task="chat",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是成长教练。只基于给定 fragments 与 profile 回答，引用来源 fragment_id。"
                            "证据不足时明确说不知道，不要编造。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(context, ensure_ascii=False),
                    },
                ],
                options=GatewayOptions(),
                user_id=user_id,
            )
        )
        return RetrievalAskResponse(
            answer=response.content,
            sources=search_result.items,
            profile_used=bool(profile_lines),
        )
