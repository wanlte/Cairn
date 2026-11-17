from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from apps.api.gateway.schemas import ProviderName


class CredentialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider: ProviderName
    api_key: str = Field(min_length=8, max_length=512)
    base_url: str | None = None
    model: str | None = None


class CredentialResponse(BaseModel):
    id: int
    name: str
    provider: ProviderName
    base_url: str | None = None
    model: str | None = None
    api_key_masked: str
    is_active: bool
    capabilities: dict | None = None
    created_at: datetime


class CapabilityView(BaseModel):
    provider: ProviderName
    json_schema: bool
    structured_output: str
    tools: str
    thinking: str
    context_window: int
    max_output_tokens: int
    qps: int
    concurrency: int
    probed: bool


class QuickSavedCredential(BaseModel):
    id: int
    name: str
    model: str | None = None


class QuickModelOption(BaseModel):
    provider: str
    label: str
    model: str | None = None
    from_environment: bool = False
    saved: list[QuickSavedCredential] = Field(default_factory=list)


class QuickModelOptionsResponse(BaseModel):
    options: list[QuickModelOption] = Field(default_factory=list)
