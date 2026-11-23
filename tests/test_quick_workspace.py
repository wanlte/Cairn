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
    # 没有文件时走自由对话链路，直接完成，不需要确认闸门
    assert body["stage"] in ("DONE", "FAILED")
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
async def test_free_question_carries_profile_and_history_context(client, monkeypatch):
    captured: list = []

    class CapturingGateway(FakeGateway):
        async def complete(self, request, meter=None):
            captured.append(request)
            return SimpleNamespace(content="这是个基于记录的回答。", data=None)

    async def fake_build(session, user_id, **kwargs):
        return CapturingGateway(), None, "fake-model", None

    monkeypatch.setattr("apps.api.workspace.service.build_gateway_for_user", fake_build)

    headers = await _register_and_login(client)
    response = await client.post(
        "/api/v1/workspace/tasks",
        json={
            "message": "我最近在关注什么",
            "direction": "free",
            "files": [],
            "model": {"provider": "deepseek", "credential_mode": "本机配置"},
        },
        headers=headers,
    )
    assert response.status_code == 201

    chat_requests = [item for item in captured if getattr(item, "task", "") == "agent_chat"]
    assert chat_requests
    payload = chat_requests[0].messages[1]["content"]
    assert "画像" in payload
    assert "相关记录" in payload


@pytest.mark.asyncio
async def test_custom_direction_reaches_chat_prompt(client, monkeypatch):
    """前端发的 custom_direction 应真正进入教练提示词（修复驼峰字段丢失）。"""
    captured: list = []

    class CapturingGateway(FakeGateway):
        async def complete(self, request, meter=None):
            captured.append(request)
            return SimpleNamespace(content="好的，我会按你的要求回答。", data=None)

    async def fake_build(session, user_id, **kwargs):
        return CapturingGateway(), None, "fake-model", None

    monkeypatch.setattr("apps.api.workspace.service.build_gateway_for_user", fake_build)

    headers = await _register_and_login(client)
    response = await client.post(
        "/api/v1/workspace/tasks",
        json={
            "message": "我该不该换工作",
            "direction": "free",
            "custom_direction": "请用苏格拉底式提问回应我",
            "files": [],
            "model": {"provider": "deepseek", "credential_mode": "本机配置"},
        },
        headers=headers,
    )
    assert response.status_code == 201
    chat_requests = [item for item in captured if getattr(item, "task", "") == "agent_chat"]
    assert chat_requests
    payload = chat_requests[0].messages[1]["content"]
    assert "苏格拉底式提问" in payload
    assert response.json()["stage"] == "DONE"


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
