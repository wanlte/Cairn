from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, SecretStr

from apps.api.agents.state import TaskIntent


class WorkspaceFilePayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    size: int = Field(default=0, ge=0)
    content: str = Field(default="", max_length=8 * 1024 * 1024)


class WorkspaceModelSelection(BaseModel):
    provider: str | None = None
    credential_id: int | None = None
    model: str | None = None
    credential_mode: str = "本机配置"
    temporary_api_key: SecretStr | None = Field(
        default=None, repr=False, exclude=True, json_schema_extra={"writeOnly": True}
    )
    temporary_base_url: str | None = Field(default=None, exclude=True)

    def to_credentials(self) -> dict[str, Any]:
        from apps.api.gateway.schemas import ProviderName

        provider = None
        if self.provider:
            try:
                provider = ProviderName(self.provider)
            except ValueError:
                provider = ProviderName.OPENAI_COMPAT
        return {
            "credential_id": self.credential_id,
            "provider": provider,
            "model": self.model,
            "temporary_api_key": self.temporary_api_key,
            "temporary_base_url": self.temporary_base_url,
        }


class WorkspaceTaskCreate(BaseModel):
    message: str = Field(default="", max_length=8000)
    direction: str = Field(default="free", max_length=32)
    custom_direction: str | None = Field(default=None, max_length=2000)
    files: list[WorkspaceFilePayload] = Field(default_factory=list, max_length=10)
    model: WorkspaceModelSelection = Field(default_factory=WorkspaceModelSelection)


class WorkspaceConfirmBody(BaseModel):
    confirmed: bool = True
    note: str | None = Field(default=None, max_length=2000)
    model: WorkspaceModelSelection = Field(default_factory=WorkspaceModelSelection)


class WorkspaceTaskResponse(BaseModel):
    task_id: str
    stage: str
    recommend_reason: str | None = None
    confirm_prompt: str | None = None
    result: dict[str, Any] | None = None
    report_id: int | None = None

    user_message: str | None = None
    intent: str = "free"
    direction: str | None = None
    created_at: datetime | None = None

    @classmethod
    def from_task(cls, task) -> WorkspaceTaskResponse:
        raw = task.result_json if isinstance(task.result_json, dict) else None
        return cls(
            task_id=task.task_key,
            stage=task.status,
            recommend_reason=task.recommend_reason,
            confirm_prompt=task.confirm_prompt,
            result=raw,
            report_id=raw.get("report_id") if raw else None,
            user_message=getattr(task, "user_message", None),
            intent=getattr(task, "intent", None) or "free",
            direction=getattr(task, "direction", None),
            created_at=getattr(task, "created_at", None),
        )


class WorkspaceMessageRecord(BaseModel):
    """从历史事件重建出来的一条对话消息。"""

    id: str
    role: str
    text: str
    kind: str = "text"
    bubble_id: str | None = None
    agent_state: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime | None = None


class WorkspaceHistoryResponse(BaseModel):
    task: WorkspaceTaskResponse
    messages: list[WorkspaceMessageRecord] = Field(default_factory=list)


def resolve_intent(direction: str) -> TaskIntent:
    mapping = {
        "weekly": TaskIntent.WEEKLY,
        "project": TaskIntent.PROJECT,
        "conversation": TaskIntent.CONVERSATION,
        "growth": TaskIntent.GROWTH,
        "free": TaskIntent.FREE,
    }
    return mapping.get(direction, TaskIntent.FREE)
