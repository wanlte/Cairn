from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from apps.api.gateway.credential_selection import CredentialSelection


class SimulationRequest(CredentialSelection):
    scenario: str = Field(min_length=4, max_length=1000)
    choice: str = Field(default="", max_length=1000)


class SimulationResponse(BaseModel):
    id: int
    scenario: str
    choice: str
    payload: dict
    created_at: datetime


class DecisionRequest(CredentialSelection):
    question: str = Field(min_length=4, max_length=1000)


class DecisionResponse(BaseModel):
    suggestion: str
    reasons: list[str] = Field(default_factory=list)
    first_step: str = ""


class DailyQuestionResponse(BaseModel):
    id: int
    day: date
    question: str
    answer: str
    created_at: datetime


class DailyAnswerRequest(BaseModel):
    answer: str = Field(max_length=3000)


class PairAnalysisRequest(CredentialSelection):
    pair_id: int = Field(ge=1)


class Mismatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    situation: str
    you: str
    them: str
    repair: str


class PairAnalysisResponse(BaseModel):
    pair_id: int
    summary: str
    mismatches: list[Mismatch] = Field(default_factory=list)


class ExportResponse(BaseModel):
    kind: str
    format: str
    filename: str
    content: str
