from __future__ import annotations

import time
from typing import TYPE_CHECKING

from apps.api.gateway.schemas import (
    GatewayErrorCode,
    GatewayOptions,
    GatewayRequest,
    ProviderCapabilities,
    ProviderName,
    ResponseFormat,
    ThinkingMode,
    ToolSupport,
    UnifiedError,
)
from apps.api.logging import get_logger

if TYPE_CHECKING:
    from apps.api.gateway.providers import BaseProvider

logger = get_logger()


KNOWN_CAPABILITIES: dict[ProviderName, ProviderCapabilities] = {
    ProviderName.DEEPSEEK: ProviderCapabilities(
        structured_output=ResponseFormat.JSON_OBJECT,
        json_schema=False,
        tools=ToolSupport.SUPPORTED,
        thinking=ThinkingMode.THINKING_PARAM,
        context_window=65536,
        max_output_tokens=8192,
        qps=10,
        concurrency=2500,
    ),
    ProviderName.VOLCENGINE: ProviderCapabilities(
        structured_output=ResponseFormat.JSON_SCHEMA,
        json_schema=True,
        tools=ToolSupport.SUPPORTED,
        thinking=ThinkingMode.THINKING_PARAM,
        context_window=131072,
        max_output_tokens=16384,
        qps=10,
        concurrency=100,
    ),
    ProviderName.HUNYUAN: ProviderCapabilities(
        structured_output=ResponseFormat.JSON_OBJECT,
        json_schema=False,
        tools=ToolSupport.SUPPORTED,
        thinking=ThinkingMode.REASONING_EFFORT,
        context_window=32768,
        max_output_tokens=8192,
        qps=5,
        concurrency=50,
    ),
    ProviderName.OPENAI_COMPAT: ProviderCapabilities(
        structured_output=ResponseFormat.JSON_OBJECT,
        json_schema=False,
        tools=ToolSupport.UNSUPPORTED,
        thinking=ThinkingMode.NONE,
        context_window=8192,
        max_output_tokens=2048,
        qps=5,
        concurrency=20,
    ),
}


class ProbeCache:
    def __init__(self, ttl_hours: int = 24) -> None:
        self.ttl_seconds = ttl_hours * 3600
        self._entries: dict[str, tuple[float, ProviderCapabilities]] = {}

    @staticmethod
    def key(provider: ProviderName, base_url: str, model: str) -> str:
        return f"{provider.value}|{base_url}|{model}"

    def get(self, key: str) -> ProviderCapabilities | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        created_at, capabilities = entry
        if time.monotonic() - created_at > self.ttl_seconds:
            self._entries.pop(key, None)
            return None
        return capabilities.model_copy(deep=True)

    def set(self, key: str, capabilities: ProviderCapabilities) -> None:
        self._entries[key] = (
            time.monotonic(),
            capabilities.model_copy(deep=True),
        )

    def clear(self) -> None:
        self._entries.clear()


DEFAULT_PROBE_CACHE = ProbeCache()


class CapabilityRegistry:
    def __init__(self, probe_cache: ProbeCache | None = None) -> None:
        self.probe_cache = probe_cache or DEFAULT_PROBE_CACHE

    @staticmethod
    def base(provider: ProviderName) -> ProviderCapabilities:
        return KNOWN_CAPABILITIES[provider].model_copy(deep=True)

    def get(
        self,
        provider: ProviderName,
        cache_key: str | None = None,
    ) -> ProviderCapabilities:
        if cache_key and provider == ProviderName.OPENAI_COMPAT:
            cached = self.probe_cache.get(cache_key)
            if cached:
                return cached
        return self.base(provider)

    def degrade_chain(self, capabilities: ProviderCapabilities) -> list[ResponseFormat]:
        chain: list[ResponseFormat] = []
        if capabilities.json_schema:
            chain.append(ResponseFormat.JSON_SCHEMA)
        if capabilities.structured_output in {
            ResponseFormat.JSON_OBJECT,
            ResponseFormat.JSON_SCHEMA,
        }:
            chain.append(ResponseFormat.JSON_OBJECT)
        chain.append(ResponseFormat.NONE)
        return chain


async def probe_capabilities(provider: BaseProvider) -> ProviderCapabilities:
    capabilities = provider.capabilities()
    if provider.name != ProviderName.OPENAI_COMPAT:
        return capabilities.model_copy(deep=True)

    probe_request = GatewayRequest(
        task="probe",
        messages=[
            {
                "role": "user",
                "content": "Return a JSON object with a single field named ok set to true.",
            }
        ],
        options=GatewayOptions(
            response_format=ResponseFormat.JSON_SCHEMA,
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
            max_tokens=32,
        ),
        user_id=0,
    )
    try:
        await provider.complete(probe_request)
    except UnifiedError as exc:
        if exc.code in {
            GatewayErrorCode.AUTH_FAILED,
            GatewayErrorCode.QUOTA_EXHAUSTED,
            GatewayErrorCode.MODEL_NOT_FOUND,
            GatewayErrorCode.RATE_LIMIT,
        }:
            raise
    except Exception as exc:  # noqa: BLE001 - 探测失败按“不支持 json_schema”处理
        logger.debug("capability_probe_failed", error=str(exc))
    else:
        capabilities.json_schema = True
        capabilities.structured_output = ResponseFormat.JSON_SCHEMA

    capabilities.probed = True
    return capabilities
