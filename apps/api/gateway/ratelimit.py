from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TypeVar

from aiobreaker import CircuitBreaker, CircuitBreakerError

from apps.api.config import get_settings
from apps.api.gateway.schemas import (
    GatewayErrorCode,
    ProviderCapabilities,
    ProviderName,
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

    def reset(self) -> None:
        self._buckets.clear()
        self._semaphores.clear()
        self._breakers.clear()
