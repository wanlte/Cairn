from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]+")


def redact_snippet(text: str | None, limit: int = 200) -> str | None:
    if not text:
        return None
    cleaned = _SK_PATTERN.sub("sk-****", text)
    return cleaned[:limit]


class ProviderName(str, Enum):
    DEEPSEEK = "deepseek"
    VOLCENGINE = "volcengine"
    HUNYUAN = "hunyuan"
    OPENAI_COMPAT = "openai_compat"


class ResponseFormat(str, Enum):
    NONE = "none"
    JSON_OBJECT = "json_object"
    JSON_SCHEMA = "json_schema"


class ToolSupport(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"


class ThinkingMode(str, Enum):
    THINKING_PARAM = "thinking_param"
    REASONING_EFFORT = "reasoning_effort"
    NONE = "none"


class GatewayErrorCode(str, Enum):
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AUTH_FAILED = "AUTH_FAILED"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    CONTEXT_TOO_LONG = "CONTEXT_TOO_LONG"
    SERVER_ERROR = "SERVER_ERROR"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"


ERROR_STATUS = {
    GatewayErrorCode.RATE_LIMIT: 429,
    GatewayErrorCode.QUOTA_EXHAUSTED: 402,
    GatewayErrorCode.AUTH_FAILED: 401,
    GatewayErrorCode.MODEL_NOT_FOUND: 404,
    GatewayErrorCode.CONTEXT_TOO_LONG: 400,
    GatewayErrorCode.SERVER_ERROR: 502,
    GatewayErrorCode.INVALID_OUTPUT: 502,
    GatewayErrorCode.CIRCUIT_OPEN: 503,
}

RETRYABLE_ERRORS = {
    GatewayErrorCode.RATE_LIMIT,
    GatewayErrorCode.SERVER_ERROR,
}

NOT_RETRYABLE_ERRORS = {
    GatewayErrorCode.QUOTA_EXHAUSTED,
    GatewayErrorCode.AUTH_FAILED,
    GatewayErrorCode.MODEL_NOT_FOUND,
    GatewayErrorCode.CONTEXT_TOO_LONG,
    GatewayErrorCode.INVALID_OUTPUT,
    GatewayErrorCode.CIRCUIT_OPEN,
}


class UnifiedError(Exception):
    def __init__(
        self,
        code: GatewayErrorCode | str,
        message: str,
        *,
        retryable: bool | None = None,
        status_code: int | None = None,
        raw_snippet: str | None = None,
    ) -> None:
        self.code = GatewayErrorCode(code)
        self.message = message
        self.retryable = (
            self.code in RETRYABLE_ERRORS if retryable is None else retryable
        )
        self.status_code = ERROR_STATUS[self.code] if status_code is None else status_code
        self.raw_snippet = raw_snippet
        super().__init__(message)


class ProviderCapabilities(BaseModel):
    structured_output: ResponseFormat = ResponseFormat.NONE
    json_schema: bool = False
    tools: ToolSupport = ToolSupport.UNSUPPORTED
    thinking: ThinkingMode = ThinkingMode.NONE
    context_window: int = 8192
    max_output_tokens: int = 2048
    qps: int = 5
    concurrency: int = 20
    probed: bool = False


class GatewayOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    temperature: float = 0.0
    max_tokens: int | None = None
    response_format: ResponseFormat = ResponseFormat.NONE
    output_schema: dict[str, Any] | None = Field(default=None, alias="schema")
    tools: list[dict[str, Any]] | None = None
    extra_body: dict[str, Any] = Field(default_factory=dict)
    allow_degrade: bool = False
    idempotency_key: str | None = None
    timeout_seconds: float | None = None


class GatewayRequest(BaseModel):
    task: str
    messages: list[dict[str, Any]]
    options: GatewayOptions = Field(default_factory=GatewayOptions)
    model: str | None = None
    user_id: int
    credential_id: int | None = None


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class GatewayResponse(BaseModel):
    content: str
    data: dict[str, Any] | None = None
    provider: ProviderName
    model: str
    credential_id: int | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: int = 0
    retry_count: int = 0
    fallback_from: str | None = None
    degraded: bool = False
    raw_response_snippet: str | None = None


class MeteringRecord(BaseModel):
    user_id: int
    task: str
    provider: ProviderName
    model: str
    usage: TokenUsage
    latency_ms: int
    retry_count: int
    fallback_from: str | None = None
    status: str
    error_code: str | None = None
    raw_snippet: str | None = None
    request_id: str | None = None
