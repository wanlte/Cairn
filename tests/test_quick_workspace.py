from __future__ import annotations

from types import SimpleNamespace

import pytest


class FakeGateway:
    async def complete(self, request, meter=None):
        return SimpleNamespace(content="这是个基于记录的回答。", data=None)


async def _register_and_login(client) -> dict:
    email = "ws-user@cairn.dev"
    await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_quick_options_are_friendly_and_hide_secrets(client):
    headers = await _register_and_login(client)
    response = await client.get("/api/v1/credentials/quick-options", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["options"]) == 4
    labels = {option["label"] for option in data["options"]}
    assert labels == {"深度求索", "火山引擎", "腾讯混元", "兼容接口"}
    assert "sk-" not in response.text
    assert "api_key" not in response.text


@pytest.mark.asyncio
async def test_create_task_returns_friendly_stage_and_confirm_flow(client, monkeypatch):
    async def fake_build(session, user_id, **kwargs):
        return FakeGateway(), None, "fake-model", None

    monkeypatch.setattr("apps.api.workspace.service.build_gateway_for_user", fake_build)

    headers = await _register_and_login(client)
    payload = {
        "message": "本周复盘",
        "direction": "weekly",
        "files": [],
        "model": {"provider": "deepseek", "credential_mode": "本机配置"},
    }
    response = await client.post("/api/v1/workspace/tasks", json=payload, headers=headers)
    assert response.status_code == 201
    body = response.json()
    task_key = body["task_id"]
    assert body["stage"] in ("WAITING_CONFIRM", "FAILED")
    assert body["recommend_reason"]

    status = await client.get(f"/api/v1/workspace/tasks/{task_key}", headers=headers)
    assert status.status_code == 200
    assert status.json()["stage"] in ("WAITING_CONFIRM", "FAILED", "DONE")

    if status.json()["stage"] == "WAITING_CONFIRM":
        confirm = await client.post(
            f"/api/v1/workspace/tasks/{task_key}/confirm",
            json={"confirmed": True, "model": {"credential_mode": "本机配置"}},
            headers=headers,
        )
        assert confirm.status_code == 200
        assert confirm.json()["stage"] == "DONE"


@pytest.mark.asyncio
async def test_temporary_key_not_reflected_in_task_response(client, monkeypatch):
    captured: dict = {}

    async def fake_build(session, user_id, **kwargs):
        captured.update(kwargs)
        return FakeGateway(), None, "fake-model", None

    monkeypatch.setattr("apps.api.workspace.service.build_gateway_for_user", fake_build)

    headers = await _register_and_login(client)
    payload = {
        "message": "帮我看看",
        "direction": "free",
        "files": [],
        "model": {
            "provider": "deepseek",
            "credential_mode": "临时使用",
            "temporary_api_key": "sk-super-secret-value",
        },
    }
    response = await client.post("/api/v1/workspace/tasks", json=payload, headers=headers)
    assert response.status_code == 201
    assert "sk-super-secret-value" not in response.text
    assert captured.get("temporary_api_key") is not None
    assert captured["temporary_api_key"].get_secret_value() == "sk-super-secret-value"
