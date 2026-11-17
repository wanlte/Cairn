from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from apps.api.config import Settings
from apps.api.gateway.metering import LlmCallLog
from apps.api.gateway.schemas import GatewayErrorCode, ProviderName, UnifiedError
from tests.fakes import FakeProvider, fake_response


async def create_credential(client, headers: dict[str, str]) -> int:
    response = await client.post(
        "/api/v1/credentials",
        json={
            "name": "gateway-credential",
            "provider": "deepseek",
            "api_key": "sk-gateway-api-1234",
        },
        headers={**headers, "X-Confirm-Action": "confirm"},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def auth_headers(client) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "gateway-api@x.com", "password": "password123"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "gateway-api@x.com", "password": "password123"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_api_call_chain_persists_metering_with_request_id(
    client, db_session, monkeypatch
):
    headers = await auth_headers(client)
    credential_id = await create_credential(client, headers)
    monkeypatch.setattr(
        "apps.api.gateway.router.build_provider",
        lambda **kwargs: FakeProvider(outcomes=[fake_response('{"ok": true}')]),
    )
    request_id = str(uuid4())

    response = await client.post(
        "/api/v1/gateway/complete",
        json={
            "credential_id": credential_id,
            "task": "extract",
            "messages": [{"role": "user", "content": "hi"}],
            "options": {
                "response_format": "json_object",
                "schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                },
            },
        },
        headers={**headers, "X-Request-ID": request_id},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"ok": True}
    assert response.headers["X-Request-ID"] == request_id

    log = (
        await db_session.execute(
            select(LlmCallLog).where(LlmCallLog.request_id == request_id)
        )
    ).scalar_one()
    assert log.task_type == "extract"
    assert log.provider == ProviderName.DEEPSEEK.value
    assert log.status == "ok"
    assert log.prompt_tokens == 100


async def test_api_quota_error_uses_unified_body_and_is_metered(
    client, db_session, monkeypatch
):
    headers = await auth_headers(client)
    credential_id = await create_credential(client, headers)
    monkeypatch.setattr(
        "apps.api.gateway.router.build_provider",
        lambda **kwargs: FakeProvider(
            outcomes=[UnifiedError(GatewayErrorCode.QUOTA_EXHAUSTED, "402")]
        ),
    )

    response = await client.post(
        "/api/v1/gateway/complete",
        json={
            "credential_id": credential_id,
            "task": "extract",
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers=headers,
    )

    assert response.status_code == 402
    body = response.json()
    assert body["code"] == "QUOTA_EXHAUSTED"
    assert body["retryable"] is False
    assert body["request_id"]

    logs = (await db_session.execute(select(LlmCallLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert logs[0].error_code == "QUOTA_EXHAUSTED"


async def test_api_can_use_server_environment_credential(client, monkeypatch):
    headers = await auth_headers(client)
    settings = Settings()
    settings.openai_compat_api_key = "sk-server-env-key"
    settings.openai_compat_base_url = "https://example.com/v1"
    settings.openai_compat_model = "env-model"
    monkeypatch.setattr(
        "apps.api.gateway.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "apps.api.gateway.router.build_provider",
        lambda **kwargs: FakeProvider(outcomes=[fake_response('{"ok": true}')]),
    )

    response = await client.post(
        "/api/v1/gateway/complete",
        json={
            "provider": "openai_compat",
            "task": "extract",
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["content"] == '{"ok": true}'
