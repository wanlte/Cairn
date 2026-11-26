from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.agents.intent import fallback_intent
from apps.api.agents.state import AgentResult, TaskIntent
from apps.api.agents.tools import (
    AgentToolContext,
    FileInput,
    coach_context,
    ingest_and_extract,
)
from apps.api.chat.prompt import load_chat_system_prompt
from apps.api.chat.schemas import (
    ChatDeltaFrame,
    ChatDoneFrame,
    ChatErrorFrame,
    ChatFrame,
    ChatMetaFrame,
    ChatRedirect,
    ChatRequest,
)
from apps.api.db.models.chat import ChatMessage
from apps.api.db.models.workspace import WorkspaceTask
from apps.api.gateway.factory import build_gateway_for_user
from apps.api.gateway.schemas import GatewayOptions, GatewayRequest, UnifiedError
from apps.api.gateway.service import Meter
from apps.api.ingestion.web import LinkContext, extract_link_context
from apps.api.workspace.schemas import WorkspaceTaskCreate
from apps.api.workspace.service import _has_history_evidence, get_task, new_task_key

REVIEW_INTENTS = {
    TaskIntent.WEEKLY,
    TaskIntent.PROJECT,
    TaskIntent.CONVERSATION,
    TaskIntent.GROWTH,
}
HISTORY_LIMIT = 12


def resolve_route(message: str, has_history: bool) -> ChatRedirect | None:
    """纯规则分流：改画像、具体任务、有证据的复盘都交回任务链路。"""
    decision = fallback_intent(message, [], "free", "", has_history)
    if decision.intent in {TaskIntent.PROFILE_EDIT, TaskIntent.TASK}:
        return ChatRedirect(intent=decision.intent.value, reason=decision.reason)
    if decision.intent in REVIEW_INTENTS and has_history:
        return ChatRedirect(intent=decision.intent.value, reason=decision.reason)
    return None


async def resolve(
    session: AsyncSession, user_id: int, message: str
) -> tuple[ChatRedirect | None, bool]:
    has_history = await _has_history_evidence(session, user_id)
    return resolve_route(message, has_history), has_history


def _context_text(context: dict, link: LinkContext) -> tuple[str, bool]:
    blocks: list[str] = []
    profile = context.get("画像") or []
    fragments = context.get("相关记录") or []
    if profile:
        blocks.append(
            "【画像背景】\n"
            + "\n".join(
                f"- {item.get('方面')}：{item.get('结论')}" for item in profile
            )
        )
    if fragments:
        blocks.append(
            "【相关记录】\n"
            + "\n".join(
                f"- [{item.get('kind')}] {item.get('payload')}" for item in fragments[:8]
            )
        )
    if link.notices:
        blocks.append("【链接读取情况】\n" + "\n".join(f"- {item}" for item in link.notices))
    if link.combined:
        blocks.append(f"【链接正文】\n{link.combined}")
    return "\n\n".join(blocks), bool(fragments)


async def _recent_messages(
    session: AsyncSession, user_id: int, session_id: str
) -> list[ChatMessage]:
    rows = (
        await session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.user_id == user_id,
                ChatMessage.session_id == session_id,
            )
            .order_by(ChatMessage.id.desc())
            .limit(HISTORY_LIMIT)
        )
    ).scalars().all()
    return list(reversed(rows))


async def _resolve_task(
    session: AsyncSession, user_id: int, session_id: str | None, message: str
) -> WorkspaceTask:
    if session_id:
        task = await get_task(session, user_id, session_id)
        count = await session.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .where(
                ChatMessage.user_id == user_id,
                ChatMessage.session_id == task.task_key,
            )
        )
        if not count:
            # 从任务链路创建的会话首次转入聊天：用任务标题与结果补一段历史，保持上下文连续
            if task.user_message:
                session.add(
                    ChatMessage(
                        user_id=user_id,
                        session_id=task.task_key,
                        role="user",
                        content=task.user_message,
                    )
                )
            result = task.result_json if isinstance(task.result_json, dict) else None
            if result and result.get("summary"):
                session.add(
                    ChatMessage(
                        user_id=user_id,
                        session_id=task.task_key,
                        role="assistant",
                        content=str(result["summary"]),
                    )
                )
            await session.flush()
        return task

    task = WorkspaceTask(
        task_key=new_task_key(),
        user_id=user_id,
        status="RUNNING",
        intent="free",
        direction="free",
        recommend_reason="先陪你聊聊",
        user_message=message,
    )
    session.add(task)
    await session.flush()
    return task


async def _persist_turn(
    session: AsyncSession, task: WorkspaceTask, user_id: int, content: str
) -> ChatMessage:
    row = ChatMessage(
        user_id=user_id,
        session_id=task.task_key,
        role="assistant",
        content=content,
    )
    session.add(row)
    result = AgentResult(
        kind="问答",
        title="对话",
        summary=content or "这次没有生成回答",
        suggestions=[],
        next_label="继续提问",
    )
    task.result_json = result.model_dump()
    task.status = "DONE"
    task.finished_at = datetime.now(UTC)
    await session.flush()
    await session.commit()
    return row


async def stream_chat(
    session: AsyncSession,
    user_id: int,
    payload: ChatRequest,
    *,
    meter: Meter | None = None,
    has_history: bool = True,
) -> AsyncIterator[ChatFrame]:
    """一次模型调用完成聊天：材料留在同一会话，逐块输出，最后整合记忆。"""
    credentials = payload.model.to_credentials()
    task = await _resolve_task(session, user_id, payload.session_id, payload.message)
    previous = await _recent_messages(session, user_id, task.task_key)

    material_notice = ""
    material_blocks: list[str] = []
    if payload.files:
        result = await ingest_and_extract(
            AgentToolContext(session=session, user_id=user_id, credential=credentials),
            [FileInput(name=item.name, content=item.content) for item in payload.files],
        )
        if result.ok:
            conversation_ids = list(task.conversation_ids_json or [])
            conversation_ids.extend(result.data.get("conversation_ids", []))
            task.conversation_ids_json = conversation_ids
        material_notice = result.message
        excerpts = "\n\n".join(
            f"【{item.name}】\n{item.content[:2000]}"
            for item in payload.files
            if item.content
        )
        if excerpts:
            material_blocks.append(f"【本次补充材料】\n{excerpts}")
        await session.flush()

    link = await extract_link_context(WorkspaceTaskCreate(message=payload.message))
    if has_history:
        tool_ctx = AgentToolContext(
            session=session, user_id=user_id, credential=credentials
        )
        context = await coach_context(tool_ctx, payload.message)
    else:
        context = {"画像": [], "相关记录": []}
    context_text, has_evidence = _context_text(context, link)
    if material_blocks:
        context_text = "\n\n".join(
            part for part in [*material_blocks, context_text] if part
        )
        has_evidence = True
    if material_notice:
        context_text = f"{context_text}\n\n【材料处理情况】{material_notice}".strip()
    system_prompt = load_chat_system_prompt(has_evidence)
    if context_text:
        system_prompt = f"{system_prompt}\n\n{context_text}"

    display_message = payload.message
    if payload.files:
        names = "、".join(item.name for item in payload.files)
        display_message = (
            f"{payload.message}\n【附件】{names}" if payload.message else f"【附件】{names}"
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for row in previous:
        messages.append(
            {"role": "user" if row.role == "user" else "assistant", "content": row.content}
        )
    messages.append({"role": "user", "content": display_message})

    session.add(
        ChatMessage(
            user_id=user_id,
            session_id=task.task_key,
            role="user",
            content=display_message,
        )
    )
    await session.commit()

    gateway, credential_id, model, _provider = await build_gateway_for_user(
        session, user_id, **credentials
    )
    request = GatewayRequest(
        task="chat",
        messages=messages,
        options=GatewayOptions(),
        model=model,
        user_id=user_id,
        credential_id=credential_id,
    )

    yield ChatMetaFrame(session_id=task.task_key)

    parts: list[str] = []
    error_frame: ChatErrorFrame | None = None
    try:
        async for chunk in gateway.complete_stream(request, meter=meter):
            if chunk.delta:
                parts.append(chunk.delta)
                yield ChatDeltaFrame(delta=chunk.delta)
    except asyncio.CancelledError:
        await asyncio.shield(_persist_turn(session, task, user_id, "".join(parts)))
        raise
    except UnifiedError as exc:
        error_frame = ChatErrorFrame(message=exc.message, code=exc.code.value)
    except Exception:  # noqa: BLE001 - 流式失败也要给用户可理解的帧
        error_frame = ChatErrorFrame(message="回答没能生成完成，请稍后再试", code="SERVER_ERROR")

    assistant = await _persist_turn(session, task, user_id, "".join(parts))
    if error_frame is not None:
        yield error_frame
    else:
        yield ChatDoneFrame(message_id=assistant.id)
