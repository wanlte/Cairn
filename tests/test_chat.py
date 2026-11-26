from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from apps.api.agents.tools import ToolResult
from apps.api.db.models.chat import ChatMessage
from apps.api.db.models.user import User
from apps.api.db.models.workspace import WorkspaceTask
from apps.api.gateway.schemas import (
    GatewayErrorCode,
    StreamChunk,
    TokenUsage,
    UnifiedError,
)


async def _register(client) -> dict:
    email = "chat-user@cairn.dev"
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _frames(text: str) -> list[dict]:
    result = []
    for block in text.split("\n\n"):
        line = next((item for item in block.split("\n") if item.startswith("data: ")), None)
        if line:
            result.append(json.loads(line[6:]))
    return result


class StreamingGateway:
    def __init__(self, parts=("你", "好", "呀"), error: Exception | None = None) -> None:
        self.parts = list(parts)
        self.error = error
        self.requests = []

    async def complete_stream(self, request, meter=None):
        self.requests.append(request)
        for part in self.parts:
            yield StreamChunk(delta=part)
        if self.error is not None:
            raise self.error
        yield StreamChunk(
            usage=TokenUsage(prompt_tokens=3, completion_tokens=len(self.parts))
        )


def _use_gateway(monkeypatch, gateway: StreamingGateway) -> None:
    async def fake_build(session, user_id, **kwargs):
        return gateway, None, "fake-model", None

    monkeypatch.setattr("apps.api.chat.service.build_gateway_for_user", fake_build)


@pytest.mark.asyncio
async def test_redirects_task_and_profile_edit_without_llm(client):
    headers = await _register(client)

    profile = await client.post(
        "/api/v1/workspace/chat",
        json={"message": "记住我在做 AI 产品"},
        headers=headers,
    )
    assert profile.status_code == 200
    assert profile.headers["content-type"].startswith("application/json")
    assert profile.json() == {
        "redirect": True,
        "intent": "profile_edit",
        "reason": "你说到了要修改画像里的内容",
    }

    task = await client.post(
        "/api/v1/workspace/chat",
        json={"message": "写一份清单"},
        headers=headers,
    )
    assert task.json()["redirect"] is True
    assert task.json()["intent"] == "task"


@pytest.mark.asyncio
async def test_chat_stream_persists_session_and_reuses_context(
    client, db_session, monkeypatch
):
    gateway = StreamingGateway()
    _use_gateway(monkeypatch, gateway)
    headers = await _register(client)

    response = await client.post(
        "/api/v1/workspace/chat",
        json={"message": "你好呀", "model": {"provider": "deepseek"}},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _frames(response.text)
    assert frames[0]["type"] == "meta"
    session_id = frames[0]["session_id"]
    assert session_id.startswith("task-")
    assert [frame["delta"] for frame in frames if frame["type"] == "delta"] == [
        "你",
        "好",
        "呀",
    ]
    assert frames[-1]["type"] == "done"
    assert isinstance(frames[-1]["message_id"], int)

    rows = (
        await db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
        )
    ).scalars().all()
    assert [row.role for row in rows] == ["user", "assistant"]
    assert [row.content for row in rows] == ["你好呀", "你好呀"]

    task = await db_session.scalar(
        select(WorkspaceTask).where(WorkspaceTask.task_key == session_id)
    )
    assert task is not None
    assert task.status == "DONE"
    assert task.result_json["summary"] == "你好呀"

    followup = await client.post(
        "/api/v1/workspace/chat",
        json={"message": "再说一次", "session_id": session_id},
        headers=headers,
    )
    assert followup.status_code == 200
    assert _frames(followup.text)[0]["session_id"] == session_id
    assert len(gateway.requests) == 2
    messages = gateway.requests[1].messages
    assert [item["role"] for item in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert [item["content"] for item in messages[1:]] == [
        "你好呀",
        "你好呀",
        "再说一次",
    ]
    all_rows = (
        await db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
        )
    ).scalars().all()
    assert len(all_rows) == 4


@pytest.mark.asyncio
async def test_chat_session_rebuilds_history(client, db_session, monkeypatch):
    _use_gateway(monkeypatch, StreamingGateway())
    headers = await _register(client)
    response = await client.post(
        "/api/v1/workspace/chat", json={"message": "你好呀"}, headers=headers
    )
    session_id = _frames(response.text)[0]["session_id"]

    history = await client.get(
        f"/api/v1/workspace/tasks/{session_id}/history", headers=headers
    )
    assert history.status_code == 200
    data = history.json()
    assert data["session_id"] == session_id
    assert [(item["role"], item["text"]) for item in data["messages"]] == [
        ("用户", "你好呀"),
        ("助手", "你好呀"),
    ]


@pytest.mark.asyncio
async def test_review_routes_by_history_evidence(client, monkeypatch):
    gateway = StreamingGateway(parts=["先聊聊"])
    _use_gateway(monkeypatch, gateway)
    headers = await _register(client)

    async def no_evidence(session, user_id):
        return False

    monkeypatch.setattr("apps.api.chat.service._has_history_evidence", no_evidence)
    without = await client.post(
        "/api/v1/workspace/chat", json={"message": "本周复盘"}, headers=headers
    )
    assert without.headers["content-type"].startswith("text/event-stream")
    assert [frame["delta"] for frame in _frames(without.text) if frame["type"] == "delta"] == [
        "先聊聊"
    ]

    async def with_evidence(session, user_id):
        return True

    monkeypatch.setattr("apps.api.chat.service._has_history_evidence", with_evidence)
    with_evidence_response = await client.post(
        "/api/v1/workspace/chat", json={"message": "本周复盘"}, headers=headers
    )
    assert with_evidence_response.json()["redirect"] is True
    assert with_evidence_response.json()["intent"] == "weekly"
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
async def test_partial_answer_is_persisted_on_stream_error(
    client, db_session, monkeypatch
):
    gateway = StreamingGateway(
        parts=["开头"], error=UnifiedError(GatewayErrorCode.SERVER_ERROR, "流中断")
    )
    _use_gateway(monkeypatch, gateway)
    headers = await _register(client)

    response = await client.post(
        "/api/v1/workspace/chat", json={"message": "继续"}, headers=headers
    )
    frames = _frames(response.text)
    assert [frame["type"] for frame in frames] == ["meta", "delta", "error"]
    assert frames[-1]["code"] == "SERVER_ERROR"

    rows = (
        await db_session.execute(select(ChatMessage).order_by(ChatMessage.id.desc()).limit(1))
    ).scalars().all()
    assert rows[0].role == "assistant"
    assert rows[0].content == "开头"


@pytest.mark.asyncio
async def test_material_upload_stays_in_the_same_chat_session(
    client, db_session, monkeypatch
):
    gateway = StreamingGateway()
    _use_gateway(monkeypatch, gateway)
    ingested: list[list[str]] = []

    async def fake_ingest(ctx, files):
        ingested.append([file.name for file in files])
        return ToolResult(
            ok=True,
            message="整理好了 1 份对话",
            data={"conversation_ids": [42], "turn_count": 2, "fragment_count": 3},
        )

    monkeypatch.setattr("apps.api.chat.service.ingest_and_extract", fake_ingest)
    headers = await _register(client)

    first = await client.post(
        "/api/v1/workspace/chat", json={"message": "你好"}, headers=headers
    )
    session_id = _frames(first.text)[0]["session_id"]

    second = await client.post(
        "/api/v1/workspace/chat",
        json={
            "message": "补充一份材料",
            "session_id": session_id,
            "files": [
                {"name": "a.md", "size": 80, "content": "用户: 我在尝试时间管理"}
            ],
        },
        headers=headers,
    )
    assert second.headers["content-type"].startswith("text/event-stream")
    assert _frames(second.text)[0]["session_id"] == session_id
    assert ingested == [["a.md"]]

    task = await db_session.scalar(
        select(WorkspaceTask).where(WorkspaceTask.task_key == session_id)
    )
    assert task.conversation_ids_json == [42]
    count = await db_session.scalar(
        select(func.count()).select_from(WorkspaceTask)
    )
    assert count == 1

    prompt = gateway.requests[1].messages[0]["content"]
    assert "本次补充材料" in prompt
    assert "我在尝试时间管理" in prompt
    assert "a.md" in gateway.requests[1].messages[-1]["content"]

    rows = (
        await db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
        )
    ).scalars().all()
    assert any("【附件】a.md" in row.content for row in rows if row.role == "user")


@pytest.mark.asyncio
async def test_existing_task_session_can_continue_in_chat(client, db_session, monkeypatch):
    gateway = StreamingGateway()
    _use_gateway(monkeypatch, gateway)
    headers = await _register(client)
    user = await db_session.scalar(select(User).where(User.email == "chat-user@cairn.dev"))

    task = WorkspaceTask(
        task_key="task-continued",
        user_id=user.id,
        status="DONE",
        intent="weekly",
        user_message="上次的问题",
        result_json={"summary": "上次的结果"},
    )
    db_session.add(task)
    await db_session.commit()

    response = await client.post(
        "/api/v1/workspace/chat",
        json={"message": "继续聊", "session_id": "task-continued"},
        headers=headers,
    )
    assert _frames(response.text)[0]["session_id"] == "task-continued"
    messages = gateway.requests[0].messages
    assert [item["content"] for item in messages[1:]] == [
        "上次的问题",
        "上次的结果",
        "继续聊",
    ]
