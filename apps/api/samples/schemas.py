from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CounterfactualCreate(BaseModel):
    prompt_type: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=8000)
    source_label: str | None = Field(default=None, max_length=128)


class CounterfactualResponse(BaseModel):
    id: int
    prompt_type: str
    content: str
    source_label: str | None
    created_at: datetime
