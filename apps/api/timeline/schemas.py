from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TimelineEventType(str, Enum):
    CONVERSATION = "conversation"
    TURN = "turn"
    FRAGMENT = "fragment"
    COUNTERFACTUAL = "counterfactual"
    REVIEW = "review"
    PROFILE = "profile"
    ACTION = "action"


class TimelineEvent(BaseModel):
    id: str
    event_type: TimelineEventType
    occurred_at: datetime | None = None
    time_precision: str = "INFERRED"
    title: str
    summary: str = ""
    source_type: str | None = None
    ref_id: int
    low_confidence: bool = False


class TimelineResponse(BaseModel):
    items: list[TimelineEvent] = Field(default_factory=list)
    total: int = 0
    span_days: float = 0.0
    low_precision_count: int = 0
