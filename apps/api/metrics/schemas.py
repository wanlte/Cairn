from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MetricPoint(BaseModel):
    bucket: str
    value: float


class MetricPair(BaseModel):
    label: str
    fast: float
    accurate: float
    sample: int


class FunnelStep(BaseModel):
    label: str
    count: int


class SystemMetrics(BaseModel):
    total_requests: int = 0
    success_rate: float = 0.0
    error_codes: list[dict[str, Any]] = Field(default_factory=list)
    latency_p50_ms: int = 0
    latency_p95_ms: int = 0
    task_completion_rate: float = 0.0
    stage_latency_ms: list[dict[str, Any]] = Field(default_factory=list)
    latency_trend: list[MetricPoint] = Field(default_factory=list)


class QualityMetrics(BaseModel):
    schema_pass_rate: float = 0.0
    evidence_hit_rate: float = 0.0
    profile_stability: float = 0.0
    appeal_rate: float = 0.0
    appeal_correction_rate: float = 0.0
    confidence_avg: float = 0.0
    coverage_avg: float = 0.0
    coverage_distribution: list[dict[str, Any]] = Field(default_factory=list)
    speed_accuracy: list[MetricPair] = Field(default_factory=list)


class CostMetrics(BaseModel):
    total_cost_cny: float = 0.0
    total_calls: int = 0
    total_tokens: int = 0
    retry_rate: float = 0.0
    fallback_rate: float = 0.0
    failure_rate: float = 0.0
    by_model: list[dict[str, Any]] = Field(default_factory=list)
    cost_trend: list[MetricPoint] = Field(default_factory=list)


class BehaviorMetrics(BaseModel):
    funnel: list[FunnelStep] = Field(default_factory=list)
    feature_penetration: list[dict[str, Any]] = Field(default_factory=list)
    events_by_day: list[MetricPoint] = Field(default_factory=list)


class ValueMetrics(BaseModel):
    coverage_improvement: float = 0.0
    weekly_streak: int = 0
    weekly_fills: int = 0
    export_count: int = 0
    open_api_calls: int = 0
    pair_analysis_count: int = 0


class SecurityMetrics(BaseModel):
    denied_requests: int = 0
    revoked_keys: int = 0
    consent_coverage: float = 0.0
    audit_events: int = 0
    redaction_hits: int = 0


class MetricsOverview(BaseModel):
    window_days: int
    generated_at: datetime
    system: SystemMetrics
    quality: QualityMetrics
    cost: CostMetrics
    behavior: BehaviorMetrics
    value: ValueMetrics
    security: SecurityMetrics
    headline: dict[str, Any] = Field(default_factory=dict)


class EventCreate(BaseModel):
    event_type: str = Field(min_length=2, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class EventResponse(BaseModel):
    id: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
