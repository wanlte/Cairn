from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from apps.api.config import get_settings
from apps.api.gateway.capabilities import (
    CapabilityRegistry,
    probe_capabilities,
)
from apps.api.gateway.providers import BaseProvider
from apps.api.gateway.ratelimit import GatewayLimiter, get_shared_limiter
from apps.api.gateway.schemas import (
    GatewayErrorCode,
    GatewayRequest,
    GatewayResponse,
    MeteringRecord,
    ProviderCapabilities,
    ProviderName,
    StreamChunk,
    TokenUsage,
    UnifiedError,
)
from apps.api.logging import request_id_var

Meter = Callable[[MeteringRecord], Awaitable[None]]


def _extract_json_candidate(text: str) -> str:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].strip()
    start = min((i for i in (candidate.find("{"), candidate.find("[")) if i >= 0), default=-1)
    if start > 0:
        candidate = candidate[start:]
    end = max(candidate.rfind("}"), candidate.rfind("]"))
    if end >= 0:
        candidate = candidate[: end + 1]
    return candidate.strip()


def _validate_schema(data: Any, schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise UnifiedError(
            GatewayErrorCode.INVALID_OUTPUT, "模型输出不是 JSON 对象", retryable=False
        )
    required = schema.get("required", [])
    if not isinstance(required, list):
        required = []
    missing = [key for key in required if key not in data]
    if missing:
        raise UnifiedError(
            GatewayErrorCode.INVALID_OUTPUT,
            f"模型输出缺少字段: {', '.join(str(key) for key in missing)}",
            retryable=False,
        )
    return data


def parse_structured_output(request: GatewayRequest, response: GatewayResponse) -> dict | None:
    options = request.options
    if not options.output_schema:
        return None
    try:
        data = json.loads(_extract_json_candidate(response.content))
    except (json.JSONDecodeError, TypeError) as exc:
        raise UnifiedError(
            GatewayErrorCode.INVALID_OUTPUT,
            "模型输出无法解析为 JSON",
            retryable=False,
            raw_snippet=response.raw_response_snippet,
        ) from exc
    return _validate_schema(data, options.output_schema)


class ModelGateway:
    """业务层唯一模型调用入口。"""

    def __init__(
        self,
        providers: list[BaseProvider],
        *,
        registry: CapabilityRegistry | None = None,
        limiter: GatewayLimiter | None = None,
    ) -> None:
        self.providers = list(providers)
        self.registry = registry or CapabilityRegistry()
        # 限流/熔断状态必须跨请求累积，默认取进程级单例
        self.limiter = limiter or get_shared_limiter()
        self._idempotency: dict[str, GatewayResponse] = {}
        self._settings = get_settings()

    async def probe(self, provider: BaseProvider, cache_key: str | None = None) -> ProviderCapabilities:
        capabilities = await probe_capabilities(provider)
        if cache_key and provider.name == ProviderName.OPENAI_COMPAT:
            self.registry.probe_cache.set(cache_key, capabilities)
        return capabilities

    async def complete(
        self,
        request: GatewayRequest,
        *,
        meter: Meter | None = None,
    ) -> GatewayResponse:
        idempotency_key = request.options.idempotency_key
        if idempotency_key and idempotency_key in self._idempotency:
            return self._idempotency[idempotency_key].model_copy(deep=True)
        if not self.providers:
            raise UnifiedError(
                GatewayErrorCode.SERVER_ERROR, "没有可用的模型凭证", retryable=True
            )

        started = time.perf_counter()
        total_retries = 0
        fallback_from: str | None = None
        last_error: UnifiedError | None = None

        for provider in self.providers:
            capabilities = provider.capabilities()
            self.limiter.configure(provider.name, capabilities)
            chain = self.registry.degrade_chain(capabilities)
            previous_step: str | None = None

            for response_format in chain:
                if previous_step and previous_step != response_format.value:
                    fallback_from = f"{provider.name.value}:{previous_step}"
                previous_step = response_format.value
                attempt = request.model_copy(deep=True)
                attempt.options.response_format = response_format

                try:
                    response, retries = await self._call_with_retry(provider, attempt)
                    total_retries += retries
                    response.data = parse_structured_output(attempt, response)
                    response.retry_count = total_retries
                    response.fallback_from = fallback_from
                    response.degraded = fallback_from is not None
                    await self._record(
                        meter,
                        request,
                        response,
                        status="ok",
                        retries=total_retries,
                    )
                    if idempotency_key:
                        self._idempotency[idempotency_key] = response.model_copy(deep=True)
                    return response
                except UnifiedError as exc:
                    last_error = exc
                    if exc.code in {
                        GatewayErrorCode.QUOTA_EXHAUSTED,
                        GatewayErrorCode.AUTH_FAILED,
                        GatewayErrorCode.MODEL_NOT_FOUND,
                        GatewayErrorCode.CIRCUIT_OPEN,
                    }:
                        break

            if last_error and last_error.code not in {
                GatewayErrorCode.INVALID_OUTPUT,
                GatewayErrorCode.RATE_LIMIT,
                GatewayErrorCode.SERVER_ERROR,
            }:
                break
            fallback_from = (
                f"{fallback_from} -> {provider.name.value}"
                if fallback_from
                else provider.name.value
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        error = last_error or UnifiedError(
            GatewayErrorCode.SERVER_ERROR, "所有模型供应商均不可用", retryable=True
        )
        await self._record(
            meter,
            request,
            None,
            status="failed",
            retries=total_retries,
            error=error,
            latency_ms=latency_ms,
            fallback_from=fallback_from,
        )
        raise error

    async def complete_stream(
        self,
        request: GatewayRequest,
        *,
        meter: Meter | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """自由文本流式调用：只走首个 provider，首字前可重试，流末统一计量。"""
        if not self.providers:
            raise UnifiedError(
                GatewayErrorCode.SERVER_ERROR, "没有可用的模型凭证", retryable=True
            )
        provider = self.providers[0]
        self.limiter.configure(provider.name, provider.capabilities())
        started = time.perf_counter()
        retries = 0
        usage = TokenUsage()
        emitted = False
        max_attempts = max(1, self._settings.gateway_retry_max)

        while True:
            stream = self.limiter.run_stream(
                provider.name, lambda: provider.complete_stream(request)
            )
            try:
                async for chunk in stream:
                    if chunk.delta:
                        emitted = True
                    if chunk.usage is not None:
                        usage = chunk.usage
                    yield chunk
            except Exception as exc:
                error = provider.normalize_error(exc)
                if (
                    not emitted
                    and error.code in {GatewayErrorCode.RATE_LIMIT, GatewayErrorCode.SERVER_ERROR}
                    and retries < max_attempts - 1
                ):
                    retries += 1
                    backoff = 0.01 * (2 ** (retries - 1))
                    await asyncio.sleep(backoff + random.uniform(0, backoff))
                    continue
                await self._record(
                    meter,
                    request,
                    None,
                    status="failed",
                    retries=retries,
                    error=error,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
                raise error from exc
            finally:
                await stream.aclose()
            break

        response = GatewayResponse(
            content="",
            provider=provider.name,
            model=request.model or getattr(provider, "model", "unknown"),
            usage=usage,
            latency_ms=int((time.perf_counter() - started) * 1000),
            retry_count=retries,
        )
        await self._record(meter, request, response, status="ok", retries=retries)

    async def _call_with_retry(
        self,
        provider: BaseProvider,
        request: GatewayRequest,
    ) -> tuple[GatewayResponse, int]:
        retries = 0
        max_attempts = max(1, self._settings.gateway_retry_max)
        while True:
            try:
                response = await self.limiter.run(
                    provider.name, lambda: provider.complete(request)
                )
                return response, retries
            except Exception as exc:
                error = provider.normalize_error(exc)
                if error.code in {
                    GatewayErrorCode.RATE_LIMIT,
                    GatewayErrorCode.SERVER_ERROR,
                } and retries < max_attempts - 1:
                    retries += 1
                    backoff = 0.01 * (2 ** (retries - 1))
                    await asyncio.sleep(backoff + random.uniform(0, backoff))
                    continue
                raise error from exc

    async def _record(
        self,
        meter: Meter | None,
        request: GatewayRequest,
        response: GatewayResponse | None,
        *,
        status: str,
        retries: int,
        error: UnifiedError | None = None,
        latency_ms: int | None = None,
        fallback_from: str | None = None,
    ) -> None:
        if meter is None:
            return
        snippet = None
        if response:
            snippet = response.raw_response_snippet
        elif error:
            snippet = error.raw_snippet or error.message
        await meter(
            MeteringRecord(
                user_id=request.user_id,
                task=request.task,
                provider=response.provider if response else ProviderName.OPENAI_COMPAT,
                model=response.model if response else (request.model or "unknown"),
                usage=response.usage if response else TokenUsage(),
                latency_ms=(
                    latency_ms
                    if latency_ms is not None
                    else (response.latency_ms if response else 0)
                ),
                retry_count=retries,
                fallback_from=fallback_from or (response.fallback_from if response else None),
                status=status,
                error_code=error.code.value if error else None,
                raw_snippet=snippet,
                request_id=request_id_var.get(),
            )
        )
