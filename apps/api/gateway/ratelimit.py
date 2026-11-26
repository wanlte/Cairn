from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from functools import lru_cache
from typing import TypeVar

from aiobreaker import CircuitBreaker, CircuitBreakerError, CircuitBreakerState

from apps.api.config import get_settings
from apps.api.gateway.schemas import (
    GatewayErrorCode,
    ProviderCapabilities,
    ProviderName,
    StreamChunk,
    UnifiedError,
)

T = TypeVar("T")


class TokenBucket:
    def __init__(self, rate: float, capacity: int | None = None) -> None:
        self.rate = float(rate)
        self.capacity = float(capacity or max(1, int(rate)))
        self._tokens = self.capacity
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._updated_at
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._updated_at = now
            if self._tokens < 1:
                wait_seconds = (1 - self._tokens) / self.rate
                await asyncio.sleep(wait_seconds)
                self._tokens = 0
                self._updated_at = time.monotonic()


class GatewayLimiter:
    def __init__(self) -> None:
        settings = get_settings()
        self.default_qps = settings.gateway_qps
        self.default_concurrency = settings.gateway_concurrency
        self.fail_max = settings.gateway_circuit_fail_max
        self.reset_timeout = settings.gateway_circuit_reset_seconds
        self._buckets: dict[ProviderName, TokenBucket] = {}
        self._semaphores: dict[ProviderName, asyncio.Semaphore] = {}
        self._breakers: dict[ProviderName, CircuitBreaker] = {}

    def configure(self, provider: ProviderName, capabilities: ProviderCapabilities) -> None:
        if provider not in self._buckets:
            self._buckets[provider] = TokenBucket(
                rate=max(1, capabilities.qps or self.default_qps),
                capacity=max(1, capabilities.qps or self.default_qps),
            )
        if provider not in self._semaphores:
            self._semaphores[provider] = asyncio.Semaphore(
                max(1, capabilities.concurrency or self.default_concurrency)
            )
        if provider not in self._breakers:
            self._breakers[provider] = CircuitBreaker(
                fail_max=self.fail_max,
                timeout_duration=timedelta(seconds=self.reset_timeout),
                name=f"gateway-{provider.value}",
            )

    def _breaker(self, provider: ProviderName) -> CircuitBreaker:
        return self._breakers.setdefault(
            provider,
            CircuitBreaker(
                fail_max=self.fail_max,
                timeout_duration=timedelta(seconds=self.reset_timeout),
                name=f"gateway-{provider.value}",
            ),
        )

    async def run(
        self,
        provider: ProviderName,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        bucket = self._buckets.setdefault(
            provider, TokenBucket(rate=self.default_qps, capacity=self.default_qps)
        )
        semaphore = self._semaphores.setdefault(
            provider, asyncio.Semaphore(self.default_concurrency)
        )
        breaker = self._breaker(provider)
        await bucket.acquire()
        async with semaphore:
            try:
                return await breaker.call_async(operation)
            except CircuitBreakerError as exc:
                raise UnifiedError(
                    GatewayErrorCode.CIRCUIT_OPEN,
                    "模型供应商熔断中，请稍后重试",
                    retryable=True,
                ) from exc
            except UnifiedError as exc:
                if exc.code == GatewayErrorCode.QUOTA_EXHAUSTED:
                    breaker.open()
                raise

    async def run_stream(
        self,
        provider: ProviderName,
        agen_factory: Callable[[], AsyncIterator[StreamChunk]],
    ) -> AsyncIterator[StreamChunk]:
        """令牌桶与并发信号量覆盖整个流生命周期，熔断状态手动维护。"""
        bucket = self._buckets.setdefault(
            provider, TokenBucket(rate=self.default_qps, capacity=self.default_qps)
        )
        semaphore = self._semaphores.setdefault(
            provider, asyncio.Semaphore(self.default_concurrency)
        )
        breaker = self._breaker(provider)
        await bucket.acquire()
        async with semaphore:
            if breaker.current_state == CircuitBreakerState.OPEN:
                async def _probe() -> None:
                    return None

                try:
                    await breaker.call_async(_probe)
                except CircuitBreakerError as exc:
                    raise UnifiedError(
                        GatewayErrorCode.CIRCUIT_OPEN,
                        "模型供应商熔断中，请稍后重试",
                        retryable=True,
                    ) from exc

            agen = agen_factory()
            failed = False
            try:
                while True:
                    try:
                        chunk = await agen.__anext__()
                    except StopAsyncIteration:
                        break
                    except Exception as exc:
                        failed = True
                        self._mark_stream_failure(breaker, exc)
                        raise
                    yield chunk
            finally:
                await agen.aclose()
                if not failed:
                    breaker.close()

    @staticmethod
    def _mark_stream_failure(breaker: CircuitBreaker, exc: Exception) -> None:
        """aiobreaker 不提供公开的手动计数接口，这里沿用其内部计数器。"""
        if isinstance(exc, UnifiedError) and exc.code == GatewayErrorCode.QUOTA_EXHAUSTED:
            breaker.open()
            return
        breaker._inc_counter()
        if (
            breaker.fail_counter >= breaker.fail_max
            or breaker.current_state == CircuitBreakerState.HALF_OPEN
        ):
            breaker.open()

    def reset(self) -> None:
        self._buckets.clear()
        self._semaphores.clear()
        self._breakers.clear()


@lru_cache(maxsize=1)
def get_shared_limiter() -> GatewayLimiter:
    """进程级限流/熔断单例。

    ModelGateway 按请求构建，但 QPS、并发与熔断状态必须跨请求累积，
    否则配置形同虚设；所有 gateway 实例共享同一个 limiter。
    """
    return GatewayLimiter()
