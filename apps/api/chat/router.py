from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.chat.schemas import ChatRequest
from apps.api.chat.service import resolve, stream_chat
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.gateway.metering import session_meter

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    redirect, has_history = await resolve(session, current_user.id, payload.message)
    # 会话内继续补充材料时留在当前会话，材料由 chat 服务摄入并成为可追问记忆
    if redirect is not None and not (payload.files and payload.session_id):
        return JSONResponse(content=redirect.model_dump())

    meter = session_meter(session)

    async def generate():
        async for frame in stream_chat(
            session, current_user.id, payload, meter=meter, has_history=has_history
        ):
            yield f"data: {frame.model_dump_json()}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
