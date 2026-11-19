from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.api.gateway.credential_selection import CredentialSelection


class Feasibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumption: str
    evidence: str
    risk: str
    verdict: str


class FailureMode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str
    signal: str
    countermeasure: str


class IfThen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: str
    action: str


class GoalConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_a: str
    goal_b: str
    reason: str


class AttributionLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str
    explanation: str


class PlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feasibility: Feasibility
    premortem: list[FailureMode] = Field(default_factory=list)
    two_minute: str = ""
    if_then: list[IfThen] = Field(default_factory=list)
    conflicts: list[GoalConflict] = Field(default_factory=list)
    attribution: list[AttributionLayer] = Field(default_factory=list)


PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "feasibility",
        "premortem",
        "two_minute",
        "if_then",
        "conflicts",
        "attribution",
    ],
    "properties": {
        "feasibility": {
            "type": "object",
            "properties": {
                "assumption": {"type": "string"},
                "evidence": {"type": "string"},
                "risk": {"type": "string"},
                "verdict": {"type": "string"},
            },
        },
        "premortem": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scenario": {"type": "string"},
                    "signal": {"type": "string"},
                    "countermeasure": {"type": "string"},
                },
            },
        },
        "two_minute": {"type": "string"},
        "if_then": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "condition": {"type": "string"},
                    "action": {"type": "string"},
                },
            },
        },
        "conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "goal_a": {"type": "string"},
                    "goal_b": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "attribution": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "layer": {"type": "string"},
                    "explanation": {"type": "string"},
                },
            },
        },
    },
}


class PlanGenerateRequest(CredentialSelection):
    goal: str = Field(min_length=4, max_length=500)
    fragment_limit: int = Field(default=120, ge=1, le=500)


class WeeklyFillCreate(BaseModel):
    week: str = Field(min_length=4, max_length=16)
    done: str = Field(default="", max_length=2000)
    blocked: str = Field(default="", max_length=2000)
    learning: str = Field(default="", max_length=2000)


class WeeklyFillResponse(BaseModel):
    id: int
    blueprint_id: int
    week: str
    done: str
    blocked: str
    learning: str
    created_at: datetime


class PlanResponse(BaseModel):
    id: int
    user_id: int
    goal: str
    status: str
    payload: dict
    coverage: dict = Field(default_factory=dict)
    prompt_version: str
    model: str | None = None
    provider: str | None = None
    created_at: datetime
    weekly_fills: list[WeeklyFillResponse] = Field(default_factory=list)
