from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.api.gateway.schemas import ProviderName


class FragmentKind(str, Enum):
    EVENT = "event"
    KNOWLEDGE = "knowledge"
    TRAIT = "trait"
    STATE = "state"


class OutcomeStatus(str, Enum):
    REPORTED = "REPORTED"
    UNVERIFIED = "UNVERIFIED"


class Polarity(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


class Level(str, Enum):
    HIGH = "HIGH"
    MED = "MED"
    LOW = "LOW"


class EventFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    what: str
    domain: str
    decision: str = ""
    outcome_status: OutcomeStatus
    confidence: float = Field(ge=0.0, le=1.0)


class KnowledgeFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: str
    summary: str
    category: str
    mastery_hint: str
    occurred_count: int = 1


class TraitFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trait: str
    polarity: Polarity
    evidence: str


class StateFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frustration: Level
    curiosity: Level
    clarity: Level


class ExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[EventFragment] = Field(default_factory=list)
    knowledge: list[KnowledgeFragment] = Field(default_factory=list)
    traits: list[TraitFragment] = Field(default_factory=list)
    state: StateFragment


FRAGMENT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["events", "knowledge", "traits", "state"],
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "what",
                    "domain",
                    "decision",
                    "outcome_status",
                    "confidence",
                ],
                "properties": {
                    "what": {"type": "string"},
                    "domain": {"type": "string"},
                    "decision": {"type": "string"},
                    "outcome_status": {
                        "type": "string",
                        "enum": ["REPORTED", "UNVERIFIED"],
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "knowledge": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["concept", "summary", "category", "mastery_hint"],
                "properties": {
                    "concept": {"type": "string"},
                    "summary": {"type": "string"},
                    "category": {"type": "string"},
                    "mastery_hint": {"type": "string"},
                    "occurred_count": {"type": "integer", "minimum": 1},
                },
            },
        },
        "traits": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["trait", "polarity", "evidence"],
                "properties": {
                    "trait": {"type": "string"},
                    "polarity": {
                        "type": "string",
                        "enum": ["POSITIVE", "NEGATIVE", "NEUTRAL"],
                    },
                    "evidence": {"type": "string"},
                },
            },
        },
        "state": {
            "type": "object",
            "additionalProperties": False,
            "required": ["frustration", "curiosity", "clarity"],
            "properties": {
                "frustration": {"type": "string", "enum": ["HIGH", "MED", "LOW"]},
                "curiosity": {"type": "string", "enum": ["HIGH", "MED", "LOW"]},
                "clarity": {"type": "string", "enum": ["HIGH", "MED", "LOW"]},
            },
        },
    },
}


class ExtractionCreateRequest(BaseModel):
    conversation_id: int
    credential_id: int | None = None
    provider: ProviderName | None = None
    model: str | None = None
    max_turns: int | None = Field(default=None, ge=1, le=500)
    idempotency_key: str | None = None


class ExtractionRunResponse(BaseModel):
    id: int
    conversation_id: int
    status: str
    total: int
    processed: int
    failed: int
    prompt_version: str
    model: str | None = None
    provider: str | None = None
    error_json: list[dict] = Field(default_factory=list)
    created_at: datetime
    finished_at: datetime | None = None


class FragmentResponse(BaseModel):
    id: int
    kind: FragmentKind
    turn_pair_id: int
    payload: dict
    content_hash: str
    created_at: datetime
