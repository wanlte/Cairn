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
async def test_graph_free_intent_runs_coach_not_review_even_with_files(monkeypatch):
    """自由对话只看意图：即使带附件也不跑复盘师和审核闸门。"""
    async def fake_ingest(ctx, files):
        return ToolResult(ok=True, data={"conversation_ids": [1], "turn_count": 2, "fragment_count": 3})

    async def fake_review(ctx, context, period):
        raise AssertionError("自由对话不应该调用复盘师")

    monkeypatch.setattr("apps.api.agents.nodes.ingest_and_extract", fake_ingest)
    monkeypatch.setattr("apps.api.agents.nodes.generate_review", fake_review)

    graph = build_workspace_graph(_tool_ctx(FakeGateway()))
    final = await graph.ainvoke(_state(TaskIntent.FREE, files=[{"name": "a.md", "content": "对话内容"}]))

    assert final["stage"] == "DONE"
    roles = [e["role"] for e in final["events"] if e.get("role")]
    assert "整理师" in roles
    assert "复盘师" not in roles
    assert "问答教练" in roles
    assert "审核员" not in roles
    context = _context(final)
    assert context.final_result is not None
    assert context.final_result.kind == "问答"
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


@pytest.mark.asyncio
async def test_finish_event_carries_report_preview(monkeypatch):
    async def fake_review(ctx, context, period):
        return ToolResult(
            ok=True,
            message="复盘报告写好了",
            data={"review_id": 42, "summary": "这次最值得回看的是翻页重排"},
        )

    monkeypatch.setattr("apps.api.agents.nodes.generate_review", fake_review)

    graph = build_workspace_graph(_tool_ctx(FakeGateway()))
    final = await graph.ainvoke(_state(TaskIntent.WEEKLY))

    context = _context(final)
    assert context.final_result is not None
    assert context.final_result.report_id == 42
    result_events = [event for event in final["events"] if event.get("result")]
    assert len(result_events) == 1
    assert result_events[0]["result"]["result"]["report_id"] == 42
    assert result_events[0]["confirm_prompt"]


@pytest.mark.asyncio
async def test_chat_only_skips_analysis_nodes_and_answers_directly(monkeypatch):
    """无文件的自由提问应像普通聊天：只跑整理师和教练，直接完成。"""
    async def fail_review(ctx, context, period):
        raise AssertionError("无文件聊天不应运行复盘师")

    async def fail_profile(ctx, context, period):
        raise AssertionError("无文件聊天不应运行画像师")

    monkeypatch.setattr("apps.api.agents.nodes.generate_review", fail_review)
    monkeypatch.setattr("apps.api.agents.nodes.generate_profile", fail_profile)

    graph = build_workspace_graph(_tool_ctx(FakeGateway("这是直接聊天得到的回答。")))
    final = await graph.ainvoke(_state(TaskIntent.FREE))

    assert final["stage"] == "DONE"
    roles = [e["role"] for e in final["events"] if e.get("role")]
    assert "整理师" in roles
    assert "问答教练" in roles
    assert "复盘师" not in roles
    assert "画像师" not in roles
    assert "审核员" not in roles
    context = _context(final)
    assert context.answer == "这是直接聊天得到的回答。"
    assert context.final_result is not None
    assert context.final_result.kind == "问答"
    assert context.final_result.summary == "这是直接聊天得到的回答。"
    result_events = [event for event in final["events"] if event.get("result")]
    assert len(result_events) == 1
    assert not result_events[0].get("confirm_prompt")


@pytest.mark.asyncio
async def test_failed_review_still_points_to_report(monkeypatch):
    async def fake_review(ctx, context, period):
        return ToolResult(
            ok=False,
            message="复盘没能生成，换一个模型再试试",
            data={"review_id": 77, "summary": "这次复盘没能完整写好，也可以换个模型再试一次。"},
        )

    monkeypatch.setattr("apps.api.agents.nodes.generate_review", fake_review)

    graph = build_workspace_graph(_tool_ctx(FakeGateway()))
    final = await graph.ainvoke(_state(TaskIntent.WEEKLY))

    context = _context(final)
    assert context.final_result is not None
    assert context.final_result.report_id == 77
    assert "没能完整写好" in context.final_result.summary


def test_task_response_exposes_result_and_report_id():
    from apps.api.workspace.schemas import WorkspaceTaskResponse

    task = SimpleNamespace(
        task_key="task-1",
        status="WAITING_CONFIRM",
        recommend_reason=None,
        confirm_prompt="这份结果需要你点头确认，确认后就正式保存。",
        result_json={
            "kind": "复盘",
            "title": "本周复盘 · 已完成",
            "summary": "这次最值得回看的是翻页重排",
            "suggestions": [],
            "next_label": "更新画像",
            "report_id": 42,
        },
    )
    response = WorkspaceTaskResponse.from_task(task)
    assert response.report_id == 42
    assert response.result is not None
    assert response.result["report_id"] == 42


def test_coach_keywords_extracts_search_terms():
    from apps.api.agents.tools import coach_keywords

    terms = coach_keywords("帮我复盘一下分页稳定性的问题")
    assert "分页" in terms
    assert "稳定" in terms
    assert len(terms) <= 12


def test_langchain_adapter_routes_to_gateway_complete():
    import asyncio

    from langchain_core.messages import HumanMessage

    gateway = FakeGateway("适配器回答")
    model = GatewayChatModel(gateway=gateway, user_id=1)

    async def run():
        result = await model.ainvoke([HumanMessage(content="你好")])
        return result.content

    assert asyncio.run(run()) == "适配器回答"
