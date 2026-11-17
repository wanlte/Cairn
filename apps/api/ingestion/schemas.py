from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    MARKDOWN = "markdown"
    TEXT = "text"
    DEEPSEEK_ARCHIVE = "deepseek_archive"


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class TimePrecision(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"
    INFERRED = "INFERRED"


class RawItem(BaseModel):
    source_item_id: str
    role: Role | None = None
    content: str
    timestamp: datetime | None = None
    time_precision: TimePrecision = TimePrecision.INFERRED
    confidence: float = 0.0
    metadata: dict = Field(default_factory=dict)


class NormalizedTurn(BaseModel):
    seq: int
    user_content: str
    assistant_content: str
    asked_at: datetime | None = None
    time_precision: TimePrecision = TimePrecision.INFERRED
    role_confidence: float = 0.0
    content_hash: str
    correction: dict | None = None


class NormalizedConversation(BaseModel):
    title: str
    source_type: SourceType
    source_ref: str
    raw_text: str
    items: list[RawItem]
    turns: list[NormalizedTurn]
    captured_at: datetime | None = None
    time_precision: TimePrecision = TimePrecision.INFERRED
    content_hash: str
    anomalies: list[str] = Field(default_factory=list)


class PreviewTurn(BaseModel):
    turn_id: str
    seq: int
    user_content: str
    assistant_content: str
    asked_at: datetime | None = None
    time_precision: TimePrecision = TimePrecision.INFERRED
    role_confidence: float = 0.0
    content_hash: str
    low_confidence: bool = False


class IngestionPreview(BaseModel):
    preview_id: str
    title: str
    source_type: SourceType
    source_ref: str
    total_turns: int
    low_confidence_count: int
    anomalies: list[str]
    turns: list[PreviewTurn]


class IngestPreviewRequest(BaseModel):
    source_type: SourceType
    text: str | None = None
    base64: str | None = None
    filename: str | None = None


class TurnCorrection(BaseModel):
    turn_id: str
    user_content: str | None = None
    assistant_content: str | None = None
    asked_at: datetime | None = None
    time_precision: TimePrecision | None = None


class IngestCommitRequest(BaseModel):
    preview_id: str
    corrections: list[TurnCorrection] = Field(default_factory=list)
