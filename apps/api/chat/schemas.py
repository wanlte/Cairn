from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from apps.api.workspace.schemas import WorkspaceFilePayload, WorkspaceModelSelection


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    model: WorkspaceModelSelection = Field(default_factory=WorkspaceModelSelection)
    session_id: str | None = Field(default=None, max_length=64)
    files: list[WorkspaceFilePayload] = Field(default_factory=list, max_length=10)


class ChatRedirect(BaseModel):
    redirect: Literal[True] = True
    intent: str
    reason: str


class ChatMetaFrame(BaseModel):
    type: Literal["meta"] = "meta"
    session_id: str


class ChatDeltaFrame(BaseModel):
    type: Literal["delta"] = "delta"
    delta: str


class ChatDoneFrame(BaseModel):
    type: Literal["done"] = "done"
    message_id: int


class ChatErrorFrame(BaseModel):
    type: Literal["error"] = "error"
    message: str
    code: str | None = None


ChatFrame = ChatMetaFrame | ChatDeltaFrame | ChatDoneFrame | ChatErrorFrame
