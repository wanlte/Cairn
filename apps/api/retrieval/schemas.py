from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from apps.api.gateway.schemas import ProviderName
from apps.api.review.schemas import Verdict


class RetrievalFilters(BaseModel):
    from_date: datetime | None = None
    to_date: datetime | None = None
    domain: str | None = None
    platform: str | None = None
    verdict: Verdict | None = None


class RetrievalCredentials(BaseModel):
    credential_id: int | None = None
    provider: ProviderName | None = None
    model: str | None = None


class RetrievalIndexRequest(RetrievalCredentials):
    limit: int = Field(default=500, ge=1, le=5000)


class RetrievalSearchRequest(RetrievalCredentials):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=100)
    candidate_k: int = Field(default=50, ge=1, le=500)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    enable_vector: bool = True
    enable_bm25: bool = True
    rerank: bool = False


class RetrievalItemResponse(BaseModel):
    fragment_id: int
    kind: str
    score: float
    bm25_score: float = 0.0
    vector_score: float = 0.0
    rerank_score: float | None = None
    payload: dict
    domain: str | None = None
    platform: str | None = None
    created_at: datetime | None = None


class RetrievalSearchResponse(BaseModel):
    query: str
    items: list[RetrievalItemResponse]
    used_vector: bool
    used_bm25: bool
    reranked: bool


class RetrievalAskRequest(RetrievalSearchRequest):
    profile_aware: bool = True


class RetrievalAskResponse(BaseModel):
    answer: str
    sources: list[RetrievalItemResponse]
    profile_used: bool
