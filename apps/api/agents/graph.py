from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph

from apps.api.agents.nodes import (
    auditor_node,
    coach_node,
    finish_node,
    organizer_node,
    profile_editor_node,
    profiler_node,
    reviewer_node,
    task_node,
)
from apps.api.agents.state import TaskIntent, WorkspaceState
from apps.api.agents.tools import AgentToolContext


def _is_chat_only(state: WorkspaceState) -> bool:
    """只看意图：自由提问走轻量对话链路，带不带文件都不再强制复盘。"""
    return state.get("intent", "free") == TaskIntent.FREE.value


def _is_profile_edit(state: WorkspaceState) -> bool:
    return state.get("intent", "free") == TaskIntent.PROFILE_EDIT.value


def _is_task(state: WorkspaceState) -> bool:
    return state.get("intent", "free") == TaskIntent.TASK.value


def _needs_revision(state: WorkspaceState) -> str:
    if state.get("revision_of") == "reviewer":
        return "revise"
    return "confirm"


def _after_organizer(state: WorkspaceState) -> str:
    if _is_profile_edit(state):
        return "profile_edit"
    if _is_task(state):
        return "task"
    return "chat_answer" if _is_chat_only(state) else "review"


def _after_coach(state: WorkspaceState) -> str:
    return "chat_finish" if _is_chat_only(state) else "audit"


def build_workspace_graph(tool_ctx: AgentToolContext):
    """用 LangGraph 编排多 Agent 协作。

    四条链路：
    - 自由提问：整理 → 问答 → 直接完成；带附件也只摄入为记忆，不跑复盘。
    - 画像修改：整理 → 画像编辑（直接改 claim）→ 直接完成。
    - 通用任务：整理 → 任务执行器（从能力注册表选工具）→ 直接完成。
    - 复盘/画像生成：整理 → 复盘 → 画像 → 问答 → 审核 →（必要时回复盘）→ 确认闸门。
    """
    graph = StateGraph(WorkspaceState)

    graph.add_node("organizer", partial(organizer_node, tool_ctx=tool_ctx))
    graph.add_node("reviewer", partial(reviewer_node, tool_ctx=tool_ctx))
    graph.add_node("profiler", partial(profiler_node, tool_ctx=tool_ctx))
    graph.add_node("profile_editor", partial(profile_editor_node, tool_ctx=tool_ctx))
    graph.add_node("task", partial(task_node, tool_ctx=tool_ctx))
    graph.add_node("coach", partial(coach_node, tool_ctx=tool_ctx))
    graph.add_node("auditor", partial(auditor_node, tool_ctx=tool_ctx))
    graph.add_node("finish", partial(finish_node, tool_ctx=tool_ctx))
    graph.add_node("chat_finish", partial(finish_node, tool_ctx=tool_ctx, chat_only=True))

    graph.set_entry_point("organizer")
    graph.add_conditional_edges(
        "organizer",
        _after_organizer,
        {"chat_answer": "coach", "review": "reviewer", "profile_edit": "profile_editor", "task": "task"},
    )
    graph.add_edge("reviewer", "profiler")
    graph.add_edge("profiler", "coach")
    graph.add_edge("profile_editor", "chat_finish")
    graph.add_edge("task", "chat_finish")
    graph.add_conditional_edges(
        "coach",
        _after_coach,
        {"chat_finish": "chat_finish", "audit": "auditor"},
    )
    graph.add_conditional_edges(
        "auditor",
        _needs_revision,
        {"revise": "reviewer", "confirm": "finish"},
    )
    graph.add_edge("finish", END)
    graph.add_edge("chat_finish", END)

    return graph.compile()
