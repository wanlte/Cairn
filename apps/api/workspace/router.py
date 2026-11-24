from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.agents.events import stream_events
from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.workspace.schemas import (
    WorkspaceConfirmBody,
    WorkspaceHistoryResponse,
    WorkspaceTaskCreate,
    WorkspaceTaskPatch,
    WorkspaceTaskResponse,
    WorkspaceTidyRequest,
)
from apps.api.workspace.service import (
    build_history,
    confirm_task,
    create_task,
    get_task,
    list_tasks,
    patch_task,
    tidy_tasks,
)

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


@router.post("/tasks", response_model=WorkspaceTaskResponse, status_code=201)
async def create_workspace_task(
    payload: WorkspaceTaskCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkspaceTaskResponse:
    task = await create_task(session, current_user.id, payload)
    await session.commit()
    return WorkspaceTaskResponse.from_task(task)


@router.get("/tasks", response_model=list[WorkspaceTaskResponse])
async def list_workspace_tasks(
    limit: int = Query(default=50, ge=1, le=100),
    archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[WorkspaceTaskResponse]:
    return await list_tasks(session, current_user.id, limit, archived)


@router.post("/tasks/tidy", response_model=dict)
async def tidy_workspace_tasks(
    payload: WorkspaceTidyRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    count = await tidy_tasks(session, current_user.id, payload)
    await session.commit()
    return {"updated": count}


@router.patch("/tasks/{task_key}", response_model=WorkspaceTaskResponse)
async def patch_workspace_task(
    task_key: str,
    payload: WorkspaceTaskPatch,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkspaceTaskResponse:
    result = await patch_task(session, current_user.id, task_key, payload)
    await session.commit()
    return result


@router.get("/tasks/{task_key}/history", response_model=WorkspaceHistoryResponse)
async def workspace_task_history(
    task_key: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkspaceHistoryResponse:
    return await build_history(session, current_user.id, task_key)


@router.get("/tasks/{task_key}", response_model=WorkspaceTaskResponse)
async def get_workspace_task(
    task_key: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkspaceTaskResponse:
    task = await get_task(session, current_user.id, task_key)
    return WorkspaceTaskResponse.from_task(task)


@router.post("/tasks/{task_key}/confirm", response_model=WorkspaceTaskResponse)
async def confirm_workspace_task(
    task_key: str,
    payload: WorkspaceConfirmBody,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkspaceTaskResponse:
    task = await confirm_task(session, current_user.id, task_key, payload)
    return WorkspaceTaskResponse.from_task(task)


@router.get("/tasks/{task_key}/events")
async def workspace_task_events(
    task_key: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    task = await get_task(session, current_user.id, task_key)

    async def generate():
        async for event in stream_events(task.id):
            import json

            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
