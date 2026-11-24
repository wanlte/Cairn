from __future__ import annotations

import json

import pytest

from apps.api.agents.capabilities import REGISTRY, Capability, CapabilityArg, register
from apps.api.agents.intent import classify_intent, fallback_intent
from apps.api.agents.state import ContextBundle, TaskIntent, WorkspaceState
from apps.api.agents.tools import AgentToolContext, ToolResult
from apps.api.gateway.langchain_adapter import GatewayChatModel
from tests.fakes import FakeProvider, fake_response


class FakeGateway:
    def __init__(self, *outcomes):
        self.provider = FakeProvider(outcomes=list(outcomes))

    async def complete(self, request, meter=None):
        return await self.provider.complete(request)


def _tool_ctx(*outcomes) -> tuple[AgentToolContext, FakeGateway]:
    gateway = FakeGateway(*outcomes)
    return (
        AgentToolContext(
            session=None,
            user_id=1,
            credential={},
            model=GatewayChatModel(gateway=gateway, user_id=1),
        ),
        gateway,
    )


def _state(message: str) -> WorkspaceState:
    return WorkspaceState(
        task_key="task-task0001",
        user_id=1,
        intent=TaskIntent.TASK.value,
        user_message=message,
        files=[],
        context=ContextBundle(intent=TaskIntent.TASK, user_message=message).model_dump(mode="json"),
        events=[],
        stage="RUNNING",
    )


def test_fallback_routes_new_demand_to_task():
    decision = fallback_intent(
        "把这些对话做成一份时间线",
        [],
        "free",
        "",
        True,
    )
    assert decision.intent == TaskIntent.TASK
    assert "具体" in decision.reason

    meta = fallback_intent("你是什么", ["chat.md"], "weekly", "", True)
    assert meta.intent == TaskIntent.FREE

    review = fallback_intent("本周复盘", [], "free", "", True)
    assert review.intent == TaskIntent.WEEKLY


@pytest.mark.asyncio
async def test_classify_new_demand_as_task():
    ctx, _ = _tool_ctx(
        fake_response(
            json.dumps(
                {
                    "intent": "task",
                    "reason": "用户要把对话做成时间线",
                    "use_history": True,
                    "needs_evidence": True,
                }
            )
        )
    )
    decision = await classify_intent(
        ctx,
        message="把这些对话做成一份时间线",
        file_names=[],
        direction="free",
        supplement="",
        has_history_evidence=True,
    )
    assert decision.intent == TaskIntent.TASK


def test_capability_registry_can_extend_without_graph_change():
    async def handler(ctx, context, args):
        return ToolResult(ok=True, message="好了", data={"summary": "临时能力执行完成"})

    register(Capability(name="unit_test_cap", description="测试用能力", handler=handler))
    assert "unit_test_cap" in REGISTRY

    plan = {"capability": "unit_test_cap", "args": [CapabilityArg(name="text", value="hi")], "reason": "测试"}
    assert plan["capability"] in REGISTRY


@pytest.mark.asyncio
async def test_task_node_runs_selected_capability():
    from apps.api.agents.nodes import task_node

    plan = json.dumps(
        {
            "capability": "retrieve",
            "args": [{"name": "query", "value": "AI 产品"}],
            "reason": "查历史",
        }
    )
    context, _ = _tool_ctx(fake_response(plan))

    async def fake_coach_context(ctx, message):
        return {"画像": [], "相关记录": [{"id": 1, "kind": "key_event", "payload": "{}"}]}

    from apps.api.agents import capabilities

    original = capabilities.coach_context
    capabilities.coach_context = fake_coach_context
    try:
        result = await task_node(_state("之前聊过 AI 产品吗"), context)
    finally:
        capabilities.coach_context = original

    assert result["events"][-1]["state"] == "完成"
    context_data = result["context"]
    assert "1 条相关内容" in context_data["answer"]
