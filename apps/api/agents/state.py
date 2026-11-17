from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class TaskIntent(str, Enum):
    WEEKLY = "weekly"
    PROJECT = "project"
    CONVERSATION = "conversation"
    GROWTH = "growth"
    FREE = "free"


INTENT_LABELS: dict[TaskIntent, str] = {
    TaskIntent.WEEKLY: "本周复盘",
    TaskIntent.PROJECT: "项目复盘",
    TaskIntent.CONVERSATION: "对话复盘",
    TaskIntent.GROWTH: "成长画像",
    TaskIntent.FREE: "自由提问",
}


class AgentRole(str, Enum):
    ORGANIZER = "整理师"
    REVIEWER = "复盘师"
    PROFILER = "画像师"
    COACH = "问答教练"
    AUDITOR = "审核员"


class AgentEvent(BaseModel):
    role: AgentRole | None = None
    state: str = "进行中"
    message: str
    bubble_id: str | None = None
    stage: str = "RUNNING"
    result: dict[str, Any] | None = None
    confirm_prompt: str | None = None


class ResultSuggestion(BaseModel):
    text: str


class AgentResult(BaseModel):
    kind: str
    title: str
    summary: str
    suggestions: list[str] = Field(default_factory=list)
    next_label: str | None = None


class ContextBundle(BaseModel):
    """LangGraph 节点间传递的上下文，包含每个 Agent 的中间产物。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    intent: TaskIntent = TaskIntent.FREE
    user_message: str = ""
    supplement: str = ""
    conversation_ids: list[int] = Field(default_factory=list)
    turn_count: int = 0
    fragment_count: int = 0
    review_id: int | None = None
    review_summary: str = ""
    evidence_weak: bool = False
    profile_id: int | None = None
    profile_summary: str = ""
    answer: str = ""
    revisions: int = 0
    final_result: AgentResult | None = None
    error: str | None = None


class WorkspaceState(TypedDict, total=False):
    task_key: str
    user_id: int
    intent: str
    user_message: str
    supplement: str
    files: list[dict[str, Any]]
    credential: dict[str, Any]
    context: dict[str, Any]
    events: list[dict[str, Any]]
    stage: str
    revision_of: str | None
    confirm_prompt: str | None
    confirmed: bool
    error: str | None
