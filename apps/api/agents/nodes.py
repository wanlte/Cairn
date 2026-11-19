from __future__ import annotations

import json

from apps.api.agents.state import (
    INTENT_LABELS,
    AgentEvent,
    AgentResult,
    AgentRole,
    ContextBundle,
    TaskIntent,
    WorkspaceState,
)
from apps.api.agents.tools import (
    AgentToolContext,
    FileInput,
    coach_context,
    generate_profile,
    generate_review,
    ingest_and_extract,
)


def _context(state: WorkspaceState) -> ContextBundle:
    ctx = state.get("context")
    if isinstance(ctx, ContextBundle):
        return ctx.model_copy(deep=True)
    return ContextBundle.model_validate(ctx or {})


def _write_context(updates: dict, context: ContextBundle) -> None:
    updates["context"] = context.model_dump(mode="json")


def _period(state: WorkspaceState) -> str:
    return f"ws-{state.get('task_key', 'task')[:12]}"


def _emit(state: WorkspaceState, role: AgentRole, message: str, *, done: bool = False) -> dict:
    event = AgentEvent(
        role=role,
        state="完成" if done else "进行中",
        message=message,
        bubble_id=f"{role.value}-{state.get('task_key', 'task')[:8]}",
    )
    return {"events": state.get("events", []) + [event.model_dump()]}


async def organizer_node(state: WorkspaceState, tool_ctx: AgentToolContext) -> dict:
    """整理师：摄入文件并抽取碎片。"""
    context = _context(state)
    updates: dict = _emit(state, AgentRole.ORGANIZER, "整理师正在梳理你提供的内容…")
    files = [FileInput.model_validate(item) for item in state.get("files", [])]
    if not files:
        updates.update(_emit(state, AgentRole.ORGANIZER, "没有文件，直接用你的描述继续", done=True))
        return updates
    result = await ingest_and_extract(tool_ctx, files)
    if result.ok:
        context.conversation_ids = result.data.get("conversation_ids", [])
        context.turn_count = result.data.get("turn_count", 0)
        context.fragment_count = result.data.get("fragment_count", 0)
    _write_context(updates, context)
    updates.update(_emit(state, AgentRole.ORGANIZER, result.message, done=result.ok))
    return updates


async def reviewer_node(state: WorkspaceState, tool_ctx: AgentToolContext) -> dict:
    """复盘师：生成复盘报告。"""
    context = _context(state)
    updates = _emit(state, AgentRole.REVIEWER, "复盘师正在认真回顾这段时间…")
    review_period = f"{_period(state)}-r{context.revisions}"
    result = await generate_review(tool_ctx, context, review_period)
    if result.data.get("review_id") is not None:
        context.review_id = result.data.get("review_id")
    context.review_summary = result.data.get("summary", "")
    if not result.ok:
        context.evidence_weak = True
    _write_context(updates, context)
    updates.update(_emit(state, AgentRole.REVIEWER, result.message, done=result.ok))
    return updates


async def profiler_node(state: WorkspaceState, tool_ctx: AgentToolContext) -> dict:
    """画像师：更新画像。"""
    if _intent(state) not in (TaskIntent.GROWTH, TaskIntent.WEEKLY):
        return {}
    context = _context(state)
    updates = _emit(state, AgentRole.PROFILER, "画像师正在更新你的成长画像…")
    result = await generate_profile(tool_ctx, context, _period(state))
    if result.ok:
        context.profile_id = result.data.get("profile_id")
        context.profile_summary = result.data.get("summary", "")
    _write_context(updates, context)
    updates.update(_emit(state, AgentRole.PROFILER, result.message, done=result.ok))
    return updates


async def coach_node(state: WorkspaceState, tool_ctx: AgentToolContext) -> dict:
    """问答教练：回答用户的具体问题。"""
    if _intent(state) not in (TaskIntent.FREE, TaskIntent.CONVERSATION):
        return {}
    context = _context(state)
    updates = _emit(state, AgentRole.COACH, "问答教练正在翻找相关记录…")
    context.answer = await _coach_answer(tool_ctx, state)
    _write_context(updates, context)
    updates.update(_emit(state, AgentRole.COACH, "教练已经准备好回答", done=True))
    return updates


async def auditor_node(state: WorkspaceState, tool_ctx: AgentToolContext) -> dict:
    """审核员：核对证据，决定是否需要修订，并把结论写入 confirm 闸门。"""
    context = _context(state)
    updates = _emit(state, AgentRole.AUDITOR, "审核员正在核对每一条依据…")
    weak = context.evidence_weak or (
        context.review_id is None and context.profile_id is None and not context.answer
    )
    context.evidence_weak = weak
    result = _build_result(state, context, intent=_intent(state))
    context.final_result = result
    if weak and context.revisions < 1:
        context.revisions += 1
        updates["revision_of"] = "reviewer"
        updates.update(
            _emit(state, AgentRole.AUDITOR, "有几处依据还不够，回头再补充一次", done=True)
        )
    else:
        updates["revision_of"] = None
        updates["confirm_prompt"] = "这份结果需要你点头确认，确认后就正式保存。"
        updates.update(_emit(state, AgentRole.AUDITOR, "核对完成，请你确认一下", done=True))
    _write_context(updates, context)
    return updates


def finish_node(state: WorkspaceState, tool_ctx: AgentToolContext) -> dict:
    """汇总最终结果，并把结果卡片一起推进对话流。"""
    context = _context(state)
    result_payload = (
        {"result": context.final_result.model_dump(mode="json")}
        if context.final_result is not None
        else None
    )
    return {
        "stage": "WAITING_CONFIRM",
        "events": state.get("events", [])
        + [
            AgentEvent(
                state="完成",
                message="都处理好了，请你确认一下",
                stage="WAITING_CONFIRM",
                confirm_prompt="这份结果需要你点头确认，确认后就正式保存。",
                result=result_payload,
            ).model_dump()
        ],
        "context": context.model_dump(mode="json"),
    }


def _intent(state: WorkspaceState) -> TaskIntent:
    try:
        return TaskIntent(state.get("intent", "free"))
    except ValueError:
        return TaskIntent.FREE


def _build_result(state: WorkspaceState, context: ContextBundle, *, intent: TaskIntent) -> AgentResult:
    label = INTENT_LABELS.get(intent, "自由提问")
    report_id = context.review_id
    if intent == TaskIntent.GROWTH and context.profile_id:
        return AgentResult(
            kind="画像",
            title=f"{label} · 更新完成",
            summary=context.profile_summary or "画像已经更新好了。",
            suggestions=["换个方向再看看", "继续补充对话，让画像更完整"],
            next_label="再聊几句",
            report_id=report_id,
        )
    if intent == TaskIntent.FREE and context.answer:
        return AgentResult(
            kind="问答",
            title=label,
            summary=context.answer,
            suggestions=["换个角度再问一次", "上传对话，让回答更有依据"],
            next_label="继续提问",
            report_id=report_id,
        )
    return AgentResult(
        kind="复盘",
        title=f"{label} · 已完成",
        summary=context.review_summary or "已经帮你梳理好这段时间的重点。",
        suggestions=["更新一次成长画像", "带着具体问题继续追问"],
        next_label="更新画像",
        report_id=report_id,
    )


async def _coach_answer(tool_ctx: AgentToolContext, state: WorkspaceState) -> str:
    from apps.api.gateway.schemas import GatewayOptions, GatewayRequest

    message = state.get("user_message", "") or "请帮我做个总结"
    context = await coach_context(tool_ctx, message)
    request = GatewayRequest(
        task="agent_chat",
        messages=[
            {
                "role": "system",
                "content": "你是成长教练。结合用户的成长画像和相关对话碎片回答：画像只是背景，不要照抄；结论必须有碎片支撑，证据不足时坦诚说明，不要编造。",
            },
            {
                "role": "user",
                "content": json.dumps({"问题": message, **context}, ensure_ascii=False),
            },
        ],
        options=GatewayOptions(),
        user_id=tool_ctx.user_id,
    )
    response = await tool_ctx.model.gateway.complete(request, meter=tool_ctx.model.meter)
    return response.content
