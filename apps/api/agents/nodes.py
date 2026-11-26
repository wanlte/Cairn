from __future__ import annotations

import json

from apps.api.agents.capabilities import REGISTRY, CapabilityPlan, capabilities_prompt
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


def _emit(
    state: WorkspaceState,
    role: AgentRole,
    message: str,
    *,
    done: bool = False,
    base: list[dict] | None = None,
) -> dict:
    """产出一条事件。传 base 时在其之上追加，避免同一节点内相互覆盖。"""
    event = AgentEvent(
        role=role,
        state="完成" if done else "进行中",
        message=message,
        bubble_id=f"{role.value}-{state.get('task_key', 'task')[:8]}",
    )
    existing = base if base is not None else state.get("events", [])
    return {"events": list(existing) + [event.model_dump()]}


async def organizer_node(state: WorkspaceState, tool_ctx: AgentToolContext) -> dict:
    """整理师：摄入文件并抽取碎片。"""
    context = _context(state)
    updates: dict = _emit(state, AgentRole.ORGANIZER, "整理师正在梳理你提供的内容…")
    files = [FileInput.model_validate(item) for item in state.get("files", [])]
    if not files:
        updates.update(_emit(state, AgentRole.ORGANIZER, "收到，我来看看怎么帮你", done=True, base=updates["events"]))
        return updates
    result = await ingest_and_extract(tool_ctx, files)
    if result.ok:
        context.conversation_ids = result.data.get("conversation_ids", [])
        context.turn_count = result.data.get("turn_count", 0)
        context.fragment_count = result.data.get("fragment_count", 0)
    _write_context(updates, context)
    updates.update(_emit(state, AgentRole.ORGANIZER, result.message, done=result.ok, base=updates["events"]))
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
    updates.update(_emit(state, AgentRole.REVIEWER, result.message, done=result.ok, base=updates["events"]))
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
    updates.update(_emit(state, AgentRole.PROFILER, result.message, done=result.ok, base=updates["events"]))
    return updates


async def profile_editor_node(state: WorkspaceState, tool_ctx: AgentToolContext) -> dict:
    """画像编辑：按用户自述直接改画像条目，不跑复盘链路。"""
    context = _context(state)
    from apps.api.agents.profile_edit import apply_profile_edits

    updates = _emit(state, AgentRole.PROFILER, "正在按你说的更新画像…")
    summary = await apply_profile_edits(
        tool_ctx,
        message=state.get("user_message", ""),
        supplement=state.get("supplement", ""),
        period=_period(state),
    )
    context.profile_edit_summary = summary
    context.profile_summary = summary
    _write_context(updates, context)
    updates.update(
        _emit(state, AgentRole.PROFILER, summary, done=True, base=updates["events"])
    )
    return updates


async def task_node(state: WorkspaceState, tool_ctx: AgentToolContext) -> dict:
    """通用任务：让模型从能力注册表里选一个工具，执行后由教练组织成回答。"""
    from pathlib import Path

    from apps.api.gateway.schemas import GatewayOptions, GatewayRequest, ResponseFormat

    context = _context(state)
    prompt_path = Path(__file__).resolve().parents[3] / "prompts" / "task" / "v1.txt"
    prompt = (
        prompt_path.read_text(encoding="utf-8")
        .replace("{capabilities}", capabilities_prompt())
        .replace("{capability_names}", json.dumps(list(REGISTRY), ensure_ascii=False))
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["capability", "reason"],
        "properties": {
            "capability": {"type": "string", "enum": list(REGISTRY)},
            "args": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "value"],
                    "properties": {
                        "name": {"type": "string", "maxLength": 40},
                        "value": {"type": "string", "maxLength": 2000},
                    },
                },
            },
            "reason": {"type": "string", "maxLength": 120},
        },
    }
    events = _emit(state, AgentRole.ORGANIZER, "看看这件事能用哪些能力完成")["events"]

    plan = None
    try:
        response = await tool_ctx.model.gateway.complete(
            GatewayRequest(
                task="task_plan",
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "用户请求": context.user_message,
                                "补充": context.supplement,
                                "有附件": bool(context.files),
                                "有链接正文": bool(context.link_content),
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                options=GatewayOptions(
                    response_format=ResponseFormat.JSON_SCHEMA,
                    output_schema=schema,
                    max_tokens=300,
                    timeout_seconds=12,
                ),
                user_id=tool_ctx.user_id,
            ),
            meter=tool_ctx.model.meter,
        )
        raw = response.data
        if raw is None and response.content:
            raw = json.loads(response.content)
        if raw:
            plan = CapabilityPlan.model_validate(raw)
    except Exception:  # noqa: BLE001 - 规划失败时降级为友好提示
        plan = None

    if plan is None or plan.capability not in REGISTRY:
        summary = "这个任务我暂时没有合适的工具完成，可以换个说法，或者直接告诉我你想做什么。"
        context.answer = summary
        return {"events": events, "context": context.model_dump(mode="json")}

    capability = REGISTRY[plan.capability]
    events = _emit(state, AgentRole.COACH, f"用「{capability.name}」来做这件事", base=events)["events"]
    try:
        result = await capability.handler(tool_ctx, context, plan.args)
        summary = result.data.get("summary") or result.message
    except Exception:  # noqa: BLE001 - 单个能力失败不影响整轮对话
        summary = "这件事没做成，换个说法或换个工具再试试。"

    context.answer = summary
    updates = _emit(state, AgentRole.COACH, "任务处理好了", done=True, base=events)
    _write_context(updates, context)
    return updates


async def coach_node(state: WorkspaceState, tool_ctx: AgentToolContext) -> dict:
    """问答教练：回答用户的具体问题。"""
    if _intent(state) not in (TaskIntent.FREE, TaskIntent.CONVERSATION):
        return {}
    context = _context(state)
    has_files = bool(state.get("files"))
    start_message = (
        "问答教练正在翻找相关记录…" if has_files else "问答教练正在想怎么回答…"
    )
    updates = _emit(state, AgentRole.COACH, start_message)
    context.answer = await _coach_answer(tool_ctx, state)
    _write_context(updates, context)
    updates.update(_emit(state, AgentRole.COACH, "教练已经准备好回答", done=True, base=updates["events"]))
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
            _emit(
                state,
                AgentRole.AUDITOR,
                "有几处依据还不够，回头再补充一次",
                done=True,
                base=updates["events"],
            )
        )
    else:
        updates["revision_of"] = None
        updates["confirm_prompt"] = "这份结果需要你点头确认，确认后就正式保存。"
        updates.update(
            _emit(
                state,
                AgentRole.AUDITOR,
                "核对完成，请你确认一下",
                done=True,
                base=updates["events"],
            )
        )
    _write_context(updates, context)
    return updates


def finish_node(
    state: WorkspaceState, tool_ctx: AgentToolContext, *, chat_only: bool = False
) -> dict:
    """汇总最终结果，并把结果卡片一起推进对话流。

    纯聊天不需要确认闸门：教练已经直接回答完，直接标记完成即可。
    """
    context = _context(state)
    result = context.final_result or _build_result(state, context, intent=_intent(state))
    context.final_result = result
    result_payload = {"result": result.model_dump(mode="json")}

    if chat_only:
        return {
            "stage": "DONE",
            "events": state.get("events", [])
            + [
                AgentEvent(
                    state="完成",
                    message="回答好了",
                    stage="DONE",
                    result=result_payload,
                ).model_dump()
            ],
            "context": context.model_dump(mode="json"),
        }

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
    if intent == TaskIntent.PROFILE_EDIT:
        return AgentResult(
            kind="画像",
            title="画像已更新",
            summary=context.profile_edit_summary or "画像已经按你说的改好了。",
            suggestions=["继续补充个人信息", "看看现在的画像"],
            next_label="看看画像",
            report_id=report_id,
        )
    if intent == TaskIntent.GROWTH and context.profile_id:
        return AgentResult(
            kind="画像",
            title=f"{label} · 更新完成",
            summary=context.profile_summary or "画像已经更新好了。",
            suggestions=["换个方向再看看", "继续补充对话，让画像更完整"],
            next_label="再聊几句",
            report_id=report_id,
        )
    if intent in (TaskIntent.FREE, TaskIntent.TASK):
        return AgentResult(
            kind="问答",
            title=label,
            summary=context.answer or "我还没想好怎么回答，换个说法再问问看。",
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


def _chat_system_prompt(has_evidence: bool) -> str:
    from apps.api.chat.prompt import load_chat_system_prompt

    return load_chat_system_prompt(has_evidence)


async def _coach_answer(tool_ctx: AgentToolContext, state: WorkspaceState) -> str:
    from apps.api.gateway.schemas import GatewayOptions, GatewayRequest

    message = state.get("user_message", "") or "请帮我做个总结"
    bundle = _context(state)
    if bundle.use_history:
        context = await coach_context(tool_ctx, message)
    else:
        context = {"画像": [], "相关记录": []}
    supplement = (state.get("supplement") or "").strip()
    has_evidence = bool(context.get("相关记录"))
    user_payload = {"问题": message, **context}
    if supplement:
        user_payload["补充要求"] = supplement
    if bundle.link_notices:
        user_payload["链接读取情况"] = bundle.link_notices
    if bundle.link_content:
        user_payload["链接正文"] = bundle.link_content
    request = GatewayRequest(
        task="agent_chat",
        messages=[
            {"role": "system", "content": _chat_system_prompt(has_evidence)},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        options=GatewayOptions(),
        user_id=tool_ctx.user_id,
    )
    response = await tool_ctx.model.gateway.complete(request, meter=tool_ctx.model.meter)
    return response.content
