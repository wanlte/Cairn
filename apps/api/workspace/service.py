from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.agents.events import append_event
from apps.api.agents.graph import build_workspace_graph
from apps.api.agents.state import AgentEvent, AgentResult, ContextBundle, WorkspaceState
from apps.api.agents.tools import AgentToolContext
from apps.api.db.models.workspace import WorkspaceTask, WorkspaceTaskEvent
from apps.api.errors import AppError
from apps.api.gateway.factory import build_gateway_for_user
from apps.api.gateway.langchain_adapter import GatewayChatModel
from apps.api.workspace.schemas import (
    WorkspaceConfirmBody,
    WorkspaceHistoryResponse,
    WorkspaceMessageRecord,
    WorkspaceModelSelection,
    WorkspaceTaskCreate,
    WorkspaceTaskPatch,
    WorkspaceTaskResponse,
    WorkspaceTidyRequest,
    resolve_intent,
)

RECOMMEND_REASONS = {
    "weekly": "看起来你想回顾这一段的进展，本周复盘挺合适",
    "project": "像是围绕某个项目在梳理，项目复盘会更聚焦",
    "conversation": "看到你带了对话文件，先从对话里帮你提炼重点",
    "growth": "你想更了解自己的成长轨迹，成长画像能帮上忙",
    "free": "你可以直接说说想了解什么",
}


def _task_key() -> str:
    return f"task-{secrets.token_hex(10)}"


def _recommend(payload: WorkspaceTaskCreate) -> tuple[str, str]:
    # 没有文件时一律走自由对话：没有证据支撑，复盘/画像节点只会空转，
    # 用户真正的诉求是像聊天一样直接得到回答。
    if not payload.files:
        return "free", RECOMMEND_REASONS["free"]
    source = f"{payload.message} {' '.join(file.name for file in payload.files)}".lower()
    rules = [
        ("weekly", ["本周", "这周", "一周", "周报", "weekly"]),
        ("project", ["项目", "迭代", "上线", "发布", "project"]),
        ("growth", ["画像", "成长", "职业", "profile"]),
        ("conversation", ["对话", "聊天", "会话", "chat"]),
    ]
    for key, words in rules:
        if any(word in source for word in words):
            return key, RECOMMEND_REASONS[key]
    if payload.direction and payload.direction != "free":
        return payload.direction, "按你选的方向来"
    return "conversation", RECOMMEND_REASONS["conversation"]


async def _build_tool_ctx(
    session: AsyncSession,
    user_id: int,
    selection: WorkspaceModelSelection,
) -> AgentToolContext:
    creds = selection.to_credentials()
    gateway, _cid, model, _provider = await build_gateway_for_user(session, user_id, **creds)
    model_adapter = GatewayChatModel(
        gateway=gateway,
        user_id=user_id,
        task="agent",
        model=model,
    )
    return AgentToolContext(
        session=session,
        user_id=user_id,
        credential=creds,
        model=model_adapter,
    )


def _initial_state(
    task: WorkspaceTask,
    payload: WorkspaceTaskCreate,
    intent_key: str,
) -> WorkspaceState:
    context = ContextBundle(
        intent=resolve_intent(intent_key),
        user_message=payload.message,
        supplement=payload.custom_direction or "",
    )
    return WorkspaceState(
        task_key=task.task_key,
        user_id=task.user_id,
        intent=intent_key,
        user_message=payload.message,
        supplement=context.supplement,
        files=[file.model_dump() for file in payload.files],
        context=context.model_dump(mode="json"),
        events=[],
        stage="RUNNING",
    )


async def _persist_events(session: AsyncSession, task: WorkspaceTask, events: list[dict]) -> None:
    for offset, event_data in enumerate(events, start=1):
        from apps.api.agents.state import AgentEvent

        await append_event(
            session,
            task.id,
            AgentEvent.model_validate(event_data),
            seq=task.id * 10000 + offset,
        )


async def create_task(
    session: AsyncSession, user_id: int, payload: WorkspaceTaskCreate
) -> WorkspaceTask:
    intent_key, reason = _recommend(payload)
    task = WorkspaceTask(
        task_key=_task_key(),
        user_id=user_id,
        status="RUNNING",
        intent=intent_key,
        direction=payload.direction,
        recommend_reason=reason,
        user_message=payload.message or None,
    )
    session.add(task)
    await session.flush()

    try:
        tool_ctx = await _build_tool_ctx(session, user_id, payload.model)
        graph = build_workspace_graph(tool_ctx)
        state = _initial_state(task, payload, intent_key)
        final = await graph.ainvoke(state)

        await _persist_events(session, task, final.get("events", []))
        raw_context = final["context"]
        context: ContextBundle = (
            raw_context
            if isinstance(raw_context, ContextBundle)
            else ContextBundle.model_validate(raw_context)
        )
        final_stage = final.get("stage", "WAITING_CONFIRM")
        task.status = final_stage
        if final_stage == "WAITING_CONFIRM":
            task.confirm_prompt = "这份结果需要你点头确认，确认后就正式保存。"
        result = context.final_result or AgentResult(
            kind="整理", title="已完成", summary="都处理好了", suggestions=[]
        )
        task.result_json = result.model_dump()
        task.finished_at = datetime.now(UTC)
        await session.flush()
    except Exception as exc:  # noqa: BLE001 - 失败要落库为友好状态
        task.status = "FAILED"
        task.error_code = type(exc).__name__
        await append_event(
            session,
            task.id,
            AgentEvent(state="完成", message="这一步没能完成，换个方式再试试", stage="FAILED"),
            seq=await _next_seq(session, task.id),
        )
    return task


async def get_task(session: AsyncSession, user_id: int, task_key: str) -> WorkspaceTask:
    task = (
        await session.execute(
            select(WorkspaceTask).where(
                WorkspaceTask.task_key == task_key, WorkspaceTask.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if not task:
        raise AppError("TASK_NOT_FOUND", "没有找到这次处理记录", 404)
    return task


async def list_tasks(
    session: AsyncSession, user_id: int, limit: int = 50, archived: bool = False
) -> list[WorkspaceTaskResponse]:
    """列出历史对话：置顶优先，再按最近创建倒序。默认只看未归档的。"""
    query = select(WorkspaceTask).where(WorkspaceTask.user_id == user_id)
    if archived is not None:
        query = query.where(WorkspaceTask.archived.is_(archived))
    tasks = (
        await session.execute(
            query.order_by(
                WorkspaceTask.pinned.desc(),
                WorkspaceTask.created_at.desc(),
            ).limit(limit)
        )
    ).scalars().all()
    return [WorkspaceTaskResponse.from_task(task) for task in tasks]


async def patch_task(
    session: AsyncSession, user_id: int, task_key: str, payload: WorkspaceTaskPatch
) -> WorkspaceTaskResponse:
    """整理单条历史对话：置顶或归档。"""
    task = await get_task(session, user_id, task_key)
    if payload.pinned is not None:
        task.pinned = payload.pinned
    if payload.archived is not None:
        task.archived = payload.archived
    await session.flush()
    return WorkspaceTaskResponse.from_task(task)


async def tidy_tasks(
    session: AsyncSession, user_id: int, payload: WorkspaceTidyRequest
) -> int:
    """批量整理：把选中的对话统一归档或取消归档，返回影响条数。"""
    if not payload.task_keys:
        return 0
    tasks = (
        await session.execute(
            select(WorkspaceTask).where(
                WorkspaceTask.user_id == user_id,
                WorkspaceTask.task_key.in_(payload.task_keys),
            )
        )
    ).scalars().all()
    for task in tasks:
        task.archived = payload.archived
        if payload.archived:
            task.pinned = False
    await session.flush()
    return len(tasks)


async def build_history(
    session: AsyncSession, user_id: int, task_key: str
) -> WorkspaceHistoryResponse:
    """用任务与历史事件重建一次完整对话，供前端加载后继续。"""
    task = await get_task(session, user_id, task_key)
    rows = (
        await session.execute(
            select(WorkspaceTaskEvent)
            .where(WorkspaceTaskEvent.task_id == task.id)
            .order_by(WorkspaceTaskEvent.seq)
        )
    ).scalars().all()

    messages: list[WorkspaceMessageRecord] = []
    if task.user_message:
        messages.append(
            WorkspaceMessageRecord(
                id=f"user-{task.task_key[:8]}",
                role="用户",
                text=task.user_message,
                kind="text",
                created_at=task.created_at,
            )
        )

    result_seen = False
    for row in rows:
        payload = dict(row.payload_json or {})
        if row.role:
            messages.append(
                WorkspaceMessageRecord(
                    id=row.bubble_id or f"bubble-{row.seq}",
                    role=row.role or "助手",
                    text=row.message,
                    kind="agent",
                    bubble_id=row.bubble_id or f"bubble-{row.seq}",
                    agent_state=row.role_state,
                    created_at=row.created_at,
                )
            )
        if "result" in payload and not result_seen:
            messages.append(
                WorkspaceMessageRecord(
                    id=f"result-{row.seq}",
                    role="助手",
                    text="",
                    kind="result",
                    result=payload["result"],
                    created_at=row.created_at,
                )
            )
            result_seen = True

    return WorkspaceHistoryResponse(
        task=WorkspaceTaskResponse.from_task(task), messages=messages
    )


async def confirm_task(
    session: AsyncSession, user_id: int, task_key: str, body: WorkspaceConfirmBody
) -> WorkspaceTask:
    """人工闸门恢复：确认采纳已生成的结果，或放弃本次结果。"""
    task = await get_task(session, user_id, task_key)
    if task.status not in ("WAITING_CONFIRM",):
        raise AppError("TASK_NOT_CONFIRMABLE", "这次处理暂时不需要确认", 409)

    message = "已经按你的确认保存好了" if body.confirmed else "好的，这次就先不采纳"
    await append_event(
        session,
        task.id,
        AgentEvent(
            state="完成",
            message=message,
            stage="DONE",
            result={"result": task.result_json} if body.confirmed and task.result_json else None,
        ),
        seq=await _next_seq(session, task.id),
    )
    task.status = "DONE"
    task.finished_at = datetime.now(UTC)
    await session.commit()
    return task


async def _next_seq(session: AsyncSession, task_id: int) -> int:
    from sqlalchemy import func

    from apps.api.db.models.workspace import WorkspaceTaskEvent

    current = (
        await session.execute(
            select(func.max(WorkspaceTaskEvent.seq)).where(WorkspaceTaskEvent.task_id == task_id)
        )
    ).scalar()
    return (current or 0) + 1
