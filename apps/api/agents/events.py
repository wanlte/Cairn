from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.agents.state import AgentEvent
from apps.api.db.base import SessionLocal
from apps.api.db.models.workspace import WorkspaceTaskEvent


async def append_event(session: AsyncSession, task_id: int, event: AgentEvent, seq: int) -> None:
    payload = dict(event.result or {})
    if event.confirm_prompt:
        payload["confirm_prompt"] = event.confirm_prompt
    row = WorkspaceTaskEvent(
        task_id=task_id,
        seq=seq,
        role=event.role.value if event.role else None,
        role_state=event.state,
        message=event.message,
        bubble_id=event.bubble_id,
        stage=event.stage,
        payload_json=payload or None,
    )
    session.add(row)
    await session.flush()


def event_to_dict(row: WorkspaceTaskEvent) -> dict:
    payload = dict(row.payload_json or {})
    data: dict = {
        "seq": row.seq,
        "stage": row.stage,
        "message": row.message,
    }
    if row.role:
        data["bubble"] = {
            "id": row.bubble_id or f"bubble-{row.seq}",
            "role": row.role,
            "message": row.message,
            "state": row.role_state,
        }
    if payload:
        if "confirm_prompt" in payload:
            data["confirmPrompt"] = payload["confirm_prompt"]
        if "result" in payload:
            data["result"] = payload["result"]
    return data


async def read_events_after(session: AsyncSession, task_id: int, after_seq: int) -> list[dict]:
    rows = (
        await session.execute(
            select(WorkspaceTaskEvent)
            .where(WorkspaceTaskEvent.task_id == task_id, WorkspaceTaskEvent.seq > after_seq)
            .order_by(WorkspaceTaskEvent.seq)
        )
    ).scalars().all()
    return [event_to_dict(row) for row in rows]


async def stream_events(task_id: int, poll_interval: float = 0.35) -> AsyncIterator[dict]:
    """轮询事件表并以 SSE 数据流产出，事件节流且只推送增量。"""
    last_seq = 0
    idle_ticks = 0
    max_idle_ticks = 120
    async with SessionLocal() as session:
        while True:
            batch = await read_events_after(session, task_id, last_seq)
            if batch:
                idle_ticks = 0
                for event in batch:
                    last_seq = max(last_seq, int(event.get("seq", 0)))
                    yield event
            else:
                idle_ticks += 1
                if idle_ticks >= max_idle_ticks:
                    break
            await asyncio.sleep(poll_interval)
