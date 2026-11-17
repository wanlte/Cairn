from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.api.agents.graph import build_workspace_graph
from apps.api.agents.state import ContextBundle, TaskIntent, WorkspaceState
from apps.api.agents.tools import AgentToolContext, ToolResult
from apps.api.gateway.langchain_adapter import GatewayChatModel


class FakeGateway:
    def __init__(self, content: str = "这是一个基于记录的回答。") -> None:
        self.content = content

    async def complete(self, request, meter=None):
        return SimpleNamespace(content=self.content, data=None)


def _tool_ctx(gateway: FakeGateway) -> AgentToolContext:
    return AgentToolContext(
        session=None,
        user_id=1,
        credential={},
        model=GatewayChatModel(gateway=gateway, user_id=1),
    )


def _state(intent: TaskIntent, files: list[dict] | None = None) -> WorkspaceState:
    return WorkspaceState(
        task_key="task-abcdef123456",
        user_id=1,
        intent=intent.value,
        user_message="帮我梳理一下",
        files=files or [],
        context=ContextBundle(intent=intent, user_message="帮我梳理一下").model_dump(mode="json"),
        events=[],
        stage="RUNNING",
    )


def _context(final) -> ContextBundle:
    raw = final["context"]
    return raw if isinstance(raw, ContextBundle) else ContextBundle.model_validate(raw)


@pytest.mark.asyncio
async def test_graph_free_intent_runs_review_coach_audit_finish(monkeypatch):
    async def fake_ingest(ctx, files):
        return ToolResult(ok=True, data={"conversation_ids": [1], "turn_count": 2, "fragment_count": 3})

    async def fake_review(ctx, context, period):
        return ToolResult(ok=True, message="复盘写好了", data={"review_id": 9, "summary": "复盘结论：进展不错。"})

    monkeypatch.setattr("apps.api.agents.nodes.ingest_and_extract", fake_ingest)
    monkeypatch.setattr("apps.api.agents.nodes.generate_review", fake_review)

    graph = build_workspace_graph(_tool_ctx(FakeGateway()))
    final = await graph.ainvoke(_state(TaskIntent.FREE, files=[{"name": "a.md", "content": "对话内容"}]))

    assert final["stage"] == "WAITING_CONFIRM"
    roles = [e["role"] for e in final["events"] if e.get("role")]
    assert "整理师" in roles
    assert "复盘师" in roles
    assert "问答教练" in roles
    assert "审核员" in roles
    assert "画像师" not in roles
    context = _context(final)
    assert context.final_result is not None
    assert context.answer


@pytest.mark.asyncio
async def test_graph_growth_intent_runs_profiler_not_coach(monkeypatch):
    async def fake_review(ctx, context, period):
        return ToolResult(ok=True, data={"review_id": 9, "summary": "复盘结论。"})

    async def fake_profile(ctx, context, period):
        return ToolResult(ok=True, data={"profile_id": 7, "summary": "你更关注后端架构。"})

    monkeypatch.setattr("apps.api.agents.nodes.generate_review", fake_review)
    monkeypatch.setattr("apps.api.agents.nodes.generate_profile", fake_profile)

    graph = build_workspace_graph(_tool_ctx(FakeGateway()))
    final = await graph.ainvoke(_state(TaskIntent.GROWTH))

    roles = [e["role"] for e in final["events"] if e.get("role")]
    assert "画像师" in roles
    assert "问答教练" not in roles
    context = _context(final)
    assert context.final_result.kind == "画像"


@pytest.mark.asyncio
async def test_auditor_triggers_one_revision(monkeypatch):
    calls = {"review": 0}

    async def fake_review(ctx, context, period):
        calls["review"] += 1
        return ToolResult(ok=False, message="依据不足")

    monkeypatch.setattr("apps.api.agents.nodes.generate_review", fake_review)

    graph = build_workspace_graph(_tool_ctx(FakeGateway()))
    final = await graph.ainvoke(_state(TaskIntent.CONVERSATION))

    assert calls["review"] == 2
    assert final["stage"] == "WAITING_CONFIRM"
    assert "审核员" in [e["role"] for e in final["events"] if e.get("role")]


def test_langchain_adapter_routes_to_gateway_complete():
    import asyncio

    from langchain_core.messages import HumanMessage

    gateway = FakeGateway("适配器回答")
    model = GatewayChatModel(gateway=gateway, user_id=1)

    async def run():
        result = await model.ainvoke([HumanMessage(content="你好")])
        return result.content

    assert asyncio.run(run()) == "适配器回答"
