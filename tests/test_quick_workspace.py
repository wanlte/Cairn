from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from apps.api.db.models.user import User
from apps.api.db.models.workspace import WorkspaceTask, WorkspaceTaskEvent


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
async def test_files_do_not_hijack_self_intro(client, monkeypatch):
    """带文件时问「你是什么」仍然走自由对话，不调用复盘师。"""
    from apps.api.agents.tools import ToolResult

    async def fake_ingest(ctx, files):
        return ToolResult(
            ok=True,
            message="整理好了 1 份对话",
            data={"conversation_ids": [1], "turn_count": 1, "fragment_count": 1},
        )

    monkeypatch.setattr("apps.api.agents.nodes.ingest_and_extract", fake_ingest)

    class IntentAwareGateway(FakeGateway):
        async def complete(self, request, meter=None):
            if getattr(request, "task", "") == "intent":
                return SimpleNamespace(
                    content="",
                    data={
                        "intent": "free",
                        "reason": "你在问我是谁",
                        "use_history": False,
                        "needs_evidence": False,
                    },
                )
            return SimpleNamespace(content="我是 Cairn 的成长教练。", data=None)

    async def fake_build(session, user_id, **kwargs):
        return IntentAwareGateway(), None, "fake-model", None

    monkeypatch.setattr("apps.api.workspace.service.build_gateway_for_user", fake_build)

    headers = await _register_and_login(client)
    response = await client.post(
        "/api/v1/workspace/tasks",
        json={
            "message": "你是什么",
            "direction": "conversation",
            "files": [{"name": "chat.md", "size": 10, "content": "用户：你好\n助手：你好"}],
            "model": {"provider": "deepseek", "credential_mode": "本机配置"},
        },
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["intent"] == "free"
    assert body["stage"] == "DONE"
    assert body["result"]["kind"] == "问答"
    assert "Cairn" in body["result"]["summary"]

    history = await client.get(f"/api/v1/workspace/tasks/{body['task_id']}/history", headers=headers)
    roles = [item.get("role") for item in history.json()["messages"]]
    assert "复盘师" not in roles
    assert "问答教练" in roles


@pytest.mark.asyncio
async def test_new_demand_goes_to_task_not_review(client, monkeypatch):
    """「做成时间线」这类新需求走通用任务，不再被塞进复盘或普通闲聊。"""
    from apps.api.agents.capabilities import REGISTRY, Capability

    async def fake_profile_read(ctx, context, args):
        return SimpleNamespace(
            ok=True,
            message="读到了",
            data={"summary": "已经读到画像里的 2 条结论，可以据此整理时间线。"},
        )

    monkeypatch.setitem(
        REGISTRY,
        "profile_read",
        Capability(name="profile_read", description="读画像", handler=fake_profile_read),
    )

    class TaskAwareGateway(FakeGateway):
        async def complete(self, request, meter=None):
            if getattr(request, "task", "") == "intent":
                return SimpleNamespace(
                    content="",
                    data={
                        "intent": "task",
                        "reason": "用户想把对话做成时间线",
                        "use_history": True,
                        "needs_evidence": True,
                    },
                )
            if getattr(request, "task", "") == "task_plan":
                return SimpleNamespace(
                    content="",
                    data={
                        "capability": "profile_read",
                        "args": [{"name": "query", "value": "时间线"}],
                        "reason": "先读画像",
                    },
                )
            return SimpleNamespace(content="任务完成。", data=None)

    async def fake_build(session, user_id, **kwargs):
        return TaskAwareGateway(), None, "fake-model", None

    monkeypatch.setattr("apps.api.workspace.service.build_gateway_for_user", fake_build)

    headers = await _register_and_login(client)
    response = await client.post(
        "/api/v1/workspace/tasks",
        json={
            "message": "把这些对话做成一份时间线",
            "direction": "free",
            "files": [],
            "model": {"provider": "deepseek", "credential_mode": "本机配置"},
        },
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["intent"] == "task"
    assert body["stage"] == "DONE"
    assert body["result"]["kind"] == "问答"
    assert "时间线" in body["result"]["summary"]

    history = await client.get(f"/api/v1/workspace/tasks/{body['task_id']}/history", headers=headers)
    roles = [item.get("role") for item in history.json()["messages"]]
    assert "复盘师" not in roles
    assert "问答教练" in roles


@pytest.mark.asyncio
async def test_history_list_and_replay(client, db_session):
    """历史列表返回任务标题，回放能用事件重建用户消息、Agent 气泡和结果卡片。"""
    headers = await _register_and_login(client)
    user = (
        await db_session.execute(select(User).where(User.email == "ws-user@cairn.dev"))
    ).scalar_one()

    task = WorkspaceTask(
        task_key="task-history-demo1",
        user_id=user.id,
        status="DONE",
        intent="free",
        direction="free",
        user_message="上次我们聊过的拖延问题",
        result_json={
            "kind": "问答",
            "title": "自由提问",
            "summary": "上次建议你先做五分钟。",
            "suggestions": [],
            "next_label": "继续提问",
        },
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add_all([
        WorkspaceTaskEvent(
            task_id=task.id, seq=1, role="整理师", role_state="完成",
            message="整理好了", bubble_id="organizer-1", stage="RUNNING",
        ),
        WorkspaceTaskEvent(
            task_id=task.id, seq=2, role="问答教练", role_state="完成",
            message="这是历史里的回答。", bubble_id="coach-1", stage="RUNNING",
        ),
        WorkspaceTaskEvent(
            task_id=task.id, seq=3, role_state="完成", message="回答好了",
            stage="DONE", payload_json={"result": task.result_json},
        ),
    ])
    await db_session.commit()

    listing = await client.get("/api/v1/workspace/tasks", headers=headers)
    assert listing.status_code == 200
    items = listing.json()
    assert any(item["task_id"] == task.task_key for item in items)
    item = next(item for item in items if item["task_id"] == task.task_key)
    assert item["user_message"] == "上次我们聊过的拖延问题"

    history = await client.get(
        f"/api/v1/workspace/tasks/{task.task_key}/history", headers=headers
    )
    assert history.status_code == 200
    data = history.json()
    assert data["task"]["task_id"] == task.task_key
    kinds = [message["kind"] for message in data["messages"]]
    assert "text" in kinds
    assert "agent" in kinds
    assert "result" in kinds
    user_message = next(message for message in data["messages"] if message["kind"] == "text")
    assert "拖延" in user_message["text"]


@pytest.mark.asyncio
async def test_history_pin_archive_and_tidy(client, db_session):
    """历史对话可以置顶、归档，也能批量整理。"""
    from datetime import timedelta

    headers = await _register_and_login(client)
    user = (
        await db_session.execute(select(User).where(User.email == "ws-user@cairn.dev"))
    ).scalar_one()
    now = datetime.now(UTC)
    a = WorkspaceTask(task_key="task-tidy-a", user_id=user.id, status="DONE",
                      intent="free", user_message="较早的对话", created_at=now - timedelta(days=2))
    b = WorkspaceTask(task_key="task-tidy-b", user_id=user.id, status="DONE",
                      intent="free", user_message="较新的对话", created_at=now - timedelta(days=1))
    db_session.add_all([a, b])
    await db_session.commit()

    listing = (await client.get("/api/v1/workspace/tasks", headers=headers)).json()
    keys = [item["task_id"] for item in listing if item["task_id"] in ("task-tidy-a", "task-tidy-b")]
    assert keys == ["task-tidy-b", "task-tidy-a"]

    pinned = await client.patch(
        "/api/v1/workspace/tasks/task-tidy-a", json={"pinned": True}, headers=headers
    )
    assert pinned.status_code == 200
    assert pinned.json()["pinned"] is True

    listing = (await client.get("/api/v1/workspace/tasks", headers=headers)).json()
    keys = [item["task_id"] for item in listing if item["task_id"] in ("task-tidy-a", "task-tidy-b")]
    assert keys == ["task-tidy-a", "task-tidy-b"]

    tidied = await client.post(
        "/api/v1/workspace/tasks/tidy",
        json={"task_keys": ["task-tidy-a"], "archived": True},
        headers=headers,
    )
    assert tidied.status_code == 200
    assert tidied.json()["updated"] == 1

    active = (await client.get("/api/v1/workspace/tasks", headers=headers)).json()
    assert "task-tidy-a" not in [item["task_id"] for item in active]
    archived = (await client.get(
        "/api/v1/workspace/tasks", params={"archived": "true"}, headers=headers
    )).json()
    archived_item = next(item for item in archived if item["task_id"] == "task-tidy-a")
    assert archived_item["archived"] is True
    assert archived_item["pinned"] is False


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
