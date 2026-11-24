from __future__ import annotations

from pydantic import BaseModel, Field

from apps.api.gateway.credential_selection import CredentialSelection


class EvaluationRunRequest(CredentialSelection):
    limit: int | None = Field(default=None, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    dataset: str | None = None


class ExtractionEvalResponse(BaseModel):
    dataset: str
    sample_count: int
    correct_fields: int
    total_fields: int
    accuracy: float
    threshold: float
    passed: bool
    failures: list[dict] = Field(default_factory=list)


class ReviewEvalResponse(BaseModel):
    dataset: str
    sample_count: int
    matched: int
    consistent: int
    consistency: float
    threshold: float
    passed: bool
    failures: list[dict] = Field(default_factory=list)


class RetrievalEvalResponse(BaseModel):
    dataset: str
    sample_count: int
    hit_at_5: int
    recall_at_5: float
    threshold: float
    passed: bool
    failures: list[dict] = Field(default_factory=list)


class DatasetInfo(BaseModel):
    name: str
    rows: int
    synthetic: bool
    description: str
