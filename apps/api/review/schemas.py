from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.api.gateway.credential_selection import CredentialSelection


class Verdict(str, Enum):
    CORRECT = "CORRECT"
    PARTIAL = "PARTIAL"
    WRONG = "WRONG"
    UNVERIFIED = "UNVERIFIED"


class Attribution(str, Enum):
    NONE = "NONE"
    KNOWLEDGE_GAP = "KNOWLEDGE_GAP"
    VERIFICATION_MISSING = "VERIFICATION_MISSING"
    ASSUMPTION_WRONG = "ASSUMPTION_WRONG"
    TIME_PRESSURE = "TIME_PRESSURE"
    COMMUNICATION = "COMMUNICATION"


class FeedbackDecision(str, Enum):
    AGREE = "AGREE"
    DISAGREE = "DISAGREE"


class DomainCount(BaseModel):
    domain: str
    count: int = 0


class TopicCount(BaseModel):
    topic: str
    count: int = 0


class OverviewSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dialogue_count: int = 0
    domain_distribution: list[DomainCount] = Field(default_factory=list)
    investment_distribution: list[TopicCount] = Field(default_factory=list)
    comparison_with_last_period: str = ""


class KeyEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fragment_id: int
    background: str
    my_judgment: str
    actual_outcome: str


class JudgmentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fragment_id: int
    verdict: Verdict
    attribution: Attribution
    reason: str
    evidence_fragment_ids: list[int] = Field(default_factory=list)


class CognitiveChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_belief: str
    new_belief: str
    evidence_fragment_ids: list[int] = Field(default_factory=list)


class ActionItemOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    verification: str
    evidence_fragment_ids: list[int] = Field(default_factory=list)


class ReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overview: OverviewSection
    key_events: list[KeyEvent] = Field(default_factory=list)
    judgments: list[JudgmentItem] = Field(default_factory=list)
    cognitive_changes: list[CognitiveChange] = Field(default_factory=list)
    action_items: list[ActionItemOutput] = Field(default_factory=list)


REVIEW_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "overview",
        "key_events",
        "judgments",
        "cognitive_changes",
        "action_items",
    ],
    "properties": {
        "overview": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "dialogue_count",
                "domain_distribution",
                "investment_distribution",
                "comparison_with_last_period",
            ],
            "properties": {
                "dialogue_count": {"type": "integer", "minimum": 0},
                "domain_distribution": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string"},
                            "count": {"type": "integer"},
                        },
                    },
                },
                "investment_distribution": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "count": {"type": "integer"},
                        },
                    },
                },
                "comparison_with_last_period": {"type": "string"},
            },
        },
        "key_events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "fragment_id",
                    "background",
                    "my_judgment",
                    "actual_outcome",
                ],
                "properties": {
                    "fragment_id": {"type": "integer"},
                    "background": {"type": "string"},
                    "my_judgment": {"type": "string"},
                    "actual_outcome": {"type": "string"},
                },
            },
        },
        "judgments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "fragment_id",
                    "verdict",
                    "attribution",
                    "reason",
                    "evidence_fragment_ids",
                ],
                "properties": {
                    "fragment_id": {"type": "integer"},
                    "verdict": {
                        "type": "string",
                        "enum": ["CORRECT", "PARTIAL", "WRONG", "UNVERIFIED"],
                    },
                    "attribution": {
                        "type": "string",
                        "enum": [
                            "NONE",
                            "KNOWLEDGE_GAP",
                            "VERIFICATION_MISSING",
                            "ASSUMPTION_WRONG",
                            "TIME_PRESSURE",
                            "COMMUNICATION",
                        ],
                    },
                    "reason": {"type": "string"},
                    "evidence_fragment_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
            },
        },
        "cognitive_changes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["old_belief", "new_belief", "evidence_fragment_ids"],
                "properties": {
                    "old_belief": {"type": "string"},
                    "new_belief": {"type": "string"},
                    "evidence_fragment_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["content", "verification", "evidence_fragment_ids"],
                "properties": {
                    "content": {"type": "string"},
                    "verification": {"type": "string"},
                    "evidence_fragment_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
            },
        },
    },
}


class ReviewCreateRequest(CredentialSelection):
    period: str = Field(min_length=1, max_length=32)
    conversation_id: int | None = None
    max_fragments: int = Field(default=200, ge=1, le=1000)
    idempotency_key: str | None = None
    direction: str | None = Field(default=None, max_length=32)
    supplement: str | None = Field(default=None, max_length=2000)


class ReviewFeedbackRequest(BaseModel):
    decision: FeedbackDecision
    note: str | None = Field(default=None, max_length=1000)


class ReviewItemResponse(BaseModel):
    id: int
    section: str
    verdict: Verdict | None = None
    attribution: Attribution | None = None
    fragment_id: int | None = None
    evidence_fragment_ids: list[int]
    payload: dict
    feedback: dict | None = None


class ActionItemStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REOPENED = "REOPENED"


class ActionItemResponse(BaseModel):
    id: int
    report_id: int
    period: str | None = None
    content: str
    verification: str
    status: ActionItemStatus = ActionItemStatus.PENDING
    verification_note: str | None = None
    evidence_fragment_ids: list[int]
    verified_at: datetime | None = None


class ActionItemVerifyRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class ReviewReportResponse(BaseModel):
    id: int
    user_id: int
    period: str
    status: str
    overview: dict
    prompt_version: str
    model: str | None = None
    provider: str | None = None
    error_code: str | None = None
    created_at: datetime
    items: list[ReviewItemResponse] = Field(default_factory=list)
    action_items: list[ActionItemResponse] = Field(default_factory=list)
