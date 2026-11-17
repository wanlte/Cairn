from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.api.gateway.schemas import ProviderName


class ProfileGroup(str, Enum):
    IDENTITY_BACKGROUND = "identity_background"
    COGNITIVE_STYLE = "cognitive_style"
    ATTENTION_TRAJECTORY = "attention_trajectory"
    HIGH_FREQUENCY_PITFALLS = "high_frequency_pitfalls"
    GROWTH_SIGNALS = "growth_signals"


class ClaimSource(str, Enum):
    MODEL = "MODEL"
    USER = "USER"


class GenericClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: str
    evidence_fragment_ids: list[int] = Field(default_factory=list)


class AttentionClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    count: int = 0
    evidence_fragment_ids: list[int] = Field(default_factory=list)


class PitfallClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pitfall: str
    count: int = 0
    evidence_fragment_ids: list[int] = Field(default_factory=list)


class GrowthClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: str
    value: str
    evidence_fragment_ids: list[int] = Field(default_factory=list)


class ProfileOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_background: list[GenericClaim] = Field(default_factory=list)
    cognitive_style: list[GenericClaim] = Field(default_factory=list)
    attention_trajectory: list[AttentionClaim] = Field(default_factory=list)
    high_frequency_pitfalls: list[PitfallClaim] = Field(default_factory=list)
    growth_signals: list[GrowthClaim] = Field(default_factory=list)


PROFILE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "identity_background",
        "cognitive_style",
        "attention_trajectory",
        "high_frequency_pitfalls",
        "growth_signals",
    ],
    "properties": {
        "identity_background": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                    "evidence_fragment_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
            },
        },
        "cognitive_style": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                    "evidence_fragment_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
            },
        },
        "attention_trajectory": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "count": {"type": "integer"},
                    "evidence_fragment_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
            },
        },
        "high_frequency_pitfalls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pitfall": {"type": "string"},
                    "count": {"type": "integer"},
                    "evidence_fragment_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
            },
        },
        "growth_signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "signal": {"type": "string"},
                    "value": {"type": "string"},
                    "evidence_fragment_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
            },
        },
    },
}


class ProfileGenerateRequest(BaseModel):
    period: str = Field(min_length=1, max_length=32)
    credential_id: int | None = None
    provider: ProviderName | None = None
    model: str | None = None
    conversation_id: int | None = None
    fragment_limit: int = Field(default=200, ge=1, le=1000)
    idempotency_key: str | None = None


class ProfileClaimUpsert(BaseModel):
    group: ProfileGroup
    key: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=2000)
    evidence_fragment_ids: list[int] = Field(default_factory=list)
    period: str | None = Field(default=None, max_length=32)


class ProfileClaimResponse(BaseModel):
    id: int
    group: ProfileGroup
    key: str
    value: str
    evidence_fragment_ids: list[int]
    source: ClaimSource
    user_corrected: bool
    is_deleted: bool
    created_at: datetime


class ProfileSnapshotResponse(BaseModel):
    id: int
    user_id: int
    period: str
    status: str
    previous_snapshot_id: int | None = None
    prompt_version: str
    model: str | None = None
    provider: str | None = None
    error_code: str | None = None
    created_at: datetime
    claims: list[ProfileClaimResponse] = Field(default_factory=list)


class ProfileDiffResponse(BaseModel):
    from_period: str
    to_period: str
    added: list[ProfileClaimResponse] = Field(default_factory=list)
    removed: list[ProfileClaimResponse] = Field(default_factory=list)
    changed: list[dict] = Field(default_factory=list)
