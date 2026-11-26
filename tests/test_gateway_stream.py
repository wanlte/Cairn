from __future__ import annotations

import pytest
from aiobreaker import CircuitBreakerState

from apps.api.gateway.ratelimit import GatewayLimiter
from apps.api.gateway.schemas import (
    GatewayErrorCode,
    GatewayOptions,
    GatewayRequest,
    ProviderCapabilities,
    ProviderName,
    StreamChunk,
    TokenUsage,
    UnifiedError,
)
from apps.api.gateway.service import ModelGateway
from tests.fakes import FakeProvider, fake_response


def make_request() -> GatewayRequest:
    return GatewayRequest(
        task="chat",
        messages=[{"role": "user", "content": "你好"}],
        options=GatewayOptions(),
        user_id=1,
    )


async def ok_stream():
    yield StreamChunk(delta="你")
    yield StreamChunk(delta="好")


async def test_run_stream_releases_semaphore_and_tracks_outcome():
    limiter = GatewayLimiter()
    limiter.configure(ProviderName.DEEPSEEK, ProviderCapabilities(qps=100, concurrency=1))

    chunks = [
        chunk
        async for chunk in limiter.run_stream(
            ProviderName.DEEPSEEK, lambda: ok_stream()
        )
    ]
    assert [chunk.delta for chunk in chunks] == ["你", "好"]
    assert limiter._semaphores[ProviderName.DEEPSEEK]._value == 1
    assert limiter._breakers[ProviderName.DEEPSEEK].fail_counter == 0

    async def broken_stream():
        yield StreamChunk(delta="部")
        raise UnifiedError(GatewayErrorCode.SERVER_ERROR, "boom")

    with pytest.raises(UnifiedError):
        [
            chunk
            async for chunk in limiter.run_stream(
                ProviderName.DEEPSEEK, lambda: broken_stream()
            )
        ]
    assert limiter._semaphores[ProviderName.DEEPSEEK]._value == 1
    assert limiter._breakers[ProviderName.DEEPSEEK].fail_counter == 1


async def test_run_stream_quota_exhausted_opens_breaker():
    limiter = GatewayLimiter()

    async def quota_stream():
        yield StreamChunk(delta="x")
        raise UnifiedError(GatewayErrorCode.QUOTA_EXHAUSTED, "余额不足")

    with pytest.raises(UnifiedError) as exc_info:
        [
            chunk
            async for chunk in limiter.run_stream(
                ProviderName.DEEPSEEK, lambda: quota_stream()
            )
        ]
    assert exc_info.value.code == GatewayErrorCode.QUOTA_EXHAUSTED
    breaker = limiter._breakers[ProviderName.DEEPSEEK]
    assert breaker.current_state == CircuitBreakerState.OPEN

    with pytest.raises(UnifiedError) as blocked:
        [
            chunk
            async for chunk in limiter.run_stream(
                ProviderName.DEEPSEEK, lambda: ok_stream()
            )
        ]
    assert blocked.value.code == GatewayErrorCode.CIRCUIT_OPEN


async def test_complete_stream_aggregates_usage_and_meters():
    response = fake_response(
        "你好世界", prompt_tokens=7, completion_tokens=3
    )
    provider = FakeProvider(outcomes=[response])
    records = []

    async def meter(record):
        records.append(record)

    chunks = [
        chunk
        async for chunk in ModelGateway([provider]).complete_stream(
            make_request(), meter=meter
        )
    ]

    assert "".join(chunk.delta or "" for chunk in chunks) == "你好世界"
    assert chunks[-1].usage == TokenUsage(prompt_tokens=7, completion_tokens=3)
    assert len(records) == 1
    assert records[0].status == "ok"
    assert records[0].usage.prompt_tokens == 7
    assert records[0].usage.completion_tokens == 3
    assert records[0].latency_ms >= 0


async def test_complete_stream_retries_only_before_first_chunk():
    provider = FakeProvider(
        outcomes=[
            UnifiedError(GatewayErrorCode.RATE_LIMIT, "429"),
            fake_response("OK"),
        ]
    )
    chunks = [
        chunk
        async for chunk in ModelGateway([provider]).complete_stream(make_request())
    ]
    assert "".join(chunk.delta or "" for chunk in chunks) == "OK"
    assert len(provider.requests) == 2

    after_first = FakeProvider(
        outcomes=[
            [
                StreamChunk(delta="甲"),
                UnifiedError(GatewayErrorCode.SERVER_ERROR, "流中断"),
            ],
            fake_response("不应重试"),
        ]
    )
    records = []

    async def meter(record):
        records.append(record)

    with pytest.raises(UnifiedError) as exc_info:
        [
            chunk
            async for chunk in ModelGateway([after_first]).complete_stream(
                make_request(), meter=meter
            )
        ]
    assert exc_info.value.code == GatewayErrorCode.SERVER_ERROR
    assert len(after_first.requests) == 1
    assert records[0].status == "failed"
