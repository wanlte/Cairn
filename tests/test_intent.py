from __future__ import annotations

import json

import pytest

from apps.api.agents.intent import (
    INTENT_JSON_SCHEMA,
    classify_intent,
    fallback_intent,
)
from apps.api.agents.state import TaskIntent
from apps.api.agents.tools import AgentToolContext
from apps.api.gateway.langchain_adapter import GatewayChatModel
from tests.fakes import FakeProvider, fake_response


def _tool_ctx(responses: list[object]) -> tuple[AgentToolContext, list]:
    provider = FakeProvider(outcomes=responses)

    class Gateway:
        async def complete(self, request, meter=None):
            return await provider.complete(request)

    ctx = AgentToolContext(
        session=None,
        user_id=1,
        credential={},
        model=GatewayChatModel(gateway=Gateway(), user_id=1),
    )
    return ctx, provider.requests


@pytest.mark.asyncio
async def test_classify_self_intro_as_free():
    ctx, requests = _tool_ctx(
        [fake_response(json.dumps({"intent": "free", "reason": "自我介绍", "use_history": False, "needs_evidence": False}))]
    )
    decision = await classify_intent(
        ctx,
        message="你是什么？",
        file_names=["chat.md"],
        direction="conversation",
        supplement="",
        has_history_evidence=True,
    )
    assert decision.intent == TaskIntent.FREE
    assert decision.use_history is False
    assert requests[0].task == "intent"
    assert requests[0].options.output_schema == INTENT_JSON_SCHEMA


@pytest.mark.asyncio
async def test_classify_profile_edit_and_fallback_on_bad_output():
    ctx, _ = _tool_ctx(
        [
            fake_response(
                json.dumps(
                    {
                        "intent": "profile_edit",
                        "reason": "你要改画像",
                        "use_history": True,
                        "needs_evidence": True,
                    }
                )
            )
        ]
    )
    decision = await classify_intent(
        ctx,
        message="记住我是做 AI 产品的",
        file_names=[],
        direction="free",
        supplement="",
        has_history_evidence=False,
    )
    assert decision.intent == TaskIntent.PROFILE_EDIT

    ctx2, _ = _tool_ctx([fake_response("这不是 JSON")])
    fallback = await classify_intent(
        ctx2,
        message="你是什么",
        file_names=["chat.md"],
        direction="conversation",
        supplement="",
        has_history_evidence=True,
    )
    assert fallback.intent == TaskIntent.FREE


def test_fallback_never_defaults_to_review_with_files():
    decision = fallback_intent(
        "帮我看看这段",
        ["豆包分享.md"],
        "free",
        "",
        True,
    )
    assert decision.intent == TaskIntent.FREE

    explicit = fallback_intent(
        "帮我做本周复盘",
        [],
        "free",
        "",
        False,
    )
    assert explicit.intent == TaskIntent.WEEKLY

    edit = fallback_intent(
        "把这条画像结论删掉",
        [],
        "free",
        "",
        False,
    )
    assert edit.intent == TaskIntent.PROFILE_EDIT
