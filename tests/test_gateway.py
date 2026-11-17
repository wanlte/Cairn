from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.gateway.capabilities import KNOWN_CAPABILITIES
from apps.api.gateway.schemas import (
    GatewayErrorCode,
    GatewayOptions,
    GatewayRequest,
    ProviderName,
    ResponseFormat,
    UnifiedError,
)
from apps.api.gateway.service import ModelGateway
from tests.fakes import FakeProvider, fake_response

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def make_request(**overrides) -> GatewayRequest:
    payload = {
        "task": "extract",
        "messages": [{"role": "user", "content": "hi"}],
        "options": GatewayOptions(
            response_format=ResponseFormat.JSON_SCHEMA,
            output_schema=SCHEMA,
        ),
        "user_id": 1,
    }
    payload.update(overrides)
    return GatewayRequest(**payload)


async def test_degradation_chain_repairs_free_text_json():
    provider = FakeProvider(
        capabilities=KNOWN_CAPABILITIES[ProviderName.DEEPSEEK],
        outcomes=[
            fake_response("非法输出"),
            fake_response('结果是 {"ok": true}'),
        ],
    )
    gateway = ModelGateway([provider])

    response = await gateway.complete(make_request())

    assert response.data == {"ok": True}
    assert response.degraded is True
    assert response.fallback_from == "deepseek:json_object"
    assert [
        item.options.response_format for item in provider.requests
    ] == [ResponseFormat.JSON_OBJECT, ResponseFormat.NONE]


async def test_retry_on_rate_limit_records_retry_count():
    provider = FakeProvider(
        outcomes=[
            UnifiedError(GatewayErrorCode.RATE_LIMIT, "429"),
            UnifiedError(GatewayErrorCode.RATE_LIMIT, "429"),
            fake_response('{"ok": true}'),
        ]
    )
    gateway = ModelGateway([provider])

    response = await gateway.complete(make_request())

    assert response.retry_count == 2
    assert len(provider.requests) == 3


async def test_quota_exhausted_is_not_retried_or_avoided():
    provider = FakeProvider(
        outcomes=[
            UnifiedError(GatewayErrorCode.QUOTA_EXHAUSTED, "402"),
            fake_response('{"ok": true}'),
        ]
    )
    gateway = ModelGateway([provider])

    with pytest.raises(UnifiedError) as exc_info:
        await gateway.complete(make_request())

    assert exc_info.value.code == GatewayErrorCode.QUOTA_EXHAUSTED
    assert len(provider.requests) == 1


async def test_fallback_to_second_provider_after_rate_limit():
    first = FakeProvider(
        outcomes=[UnifiedError(GatewayErrorCode.RATE_LIMIT, "429")] * 3
    )
    second = FakeProvider(
        name=ProviderName.VOLCENGINE,
        capabilities=KNOWN_CAPABILITIES[ProviderName.VOLCENGINE],
        outcomes=[fake_response('{"ok": true}', provider=ProviderName.VOLCENGINE)],
    )
    gateway = ModelGateway([first, second])

    response = await gateway.complete(make_request())

    assert response.provider == ProviderName.VOLCENGINE
    assert "deepseek" in (response.fallback_from or "")
    assert len(first.requests) == 3
    assert len(second.requests) >= 1


async def test_idempotency_key_prevents_duplicate_provider_calls():
    provider = FakeProvider(outcomes=[fake_response('{"ok": true}')])
    gateway = ModelGateway([provider])
    request = make_request(
        options=GatewayOptions(
            response_format=ResponseFormat.JSON_OBJECT,
            output_schema=SCHEMA,
            idempotency_key="hash-turn-pair-prompt-v1",
        )
    )

    first = await gateway.complete(request)
    second = await gateway.complete(request)

    assert first.data == second.data == {"ok": True}
    assert len(provider.requests) == 1


def test_capability_degrade_chain_matches_matrix():
    gateway = ModelGateway([])

    assert gateway.registry.degrade_chain(
        KNOWN_CAPABILITIES[ProviderName.VOLCENGINE]
    ) == [
        ResponseFormat.JSON_SCHEMA,
        ResponseFormat.JSON_OBJECT,
        ResponseFormat.NONE,
    ]
    assert gateway.registry.degrade_chain(
        KNOWN_CAPABILITIES[ProviderName.DEEPSEEK]
    ) == [ResponseFormat.JSON_OBJECT, ResponseFormat.NONE]


def test_business_modules_do_not_import_vendor_sdk():
    api_root = Path(__file__).resolve().parents[1] / "apps" / "api"
    offenders = []
    for path in api_root.rglob("*.py"):
        if path.parts[-2:] == ("gateway", "providers.py"):
            continue
        text = path.read_text(encoding="utf-8")
        if "import openai" in text or "from openai" in text:
            offenders.append(str(path))
    assert offenders == []
