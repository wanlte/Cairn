from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=lambda: ["profile:read"])
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class ApiKeyCreated(ApiKeyResponse):
    token: str


class ConsentGrant(BaseModel):
    consent_type: str = Field(min_length=1, max_length=64)
    version: str = Field(default="v1", max_length=32)
    counterpart_id: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ConsentResponse(BaseModel):
    id: int
    consent_type: str
    version: str
    counterpart_id: int | None
    granted: bool
    granted_at: datetime
    revoked_at: datetime | None


class PairCreate(BaseModel):
    counterpart_email: str = Field(min_length=3, max_length=255)
    note: str | None = Field(default=None, max_length=1000)


class PairResponse(BaseModel):
    id: int
    user_a_id: int
    user_b_id: int
    status: str
    created_by: int
    note: str | None
    confirmed_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class AuditLogResponse(BaseModel):
    id: int
    user_id: int | None
    actor_type: str
    action: str
    target_type: str | None
    target_id: str | None
    request_id: str | None
    metadata: dict[str, Any]
    created_at: datetime
