from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph

from apps.api.agents.nodes import (
    auditor_node,
    coach_node,
    finish_node,
    organizer_node,
    profiler_node,
    reviewer_node,
)
from apps.api.agents.state import TaskIntent, WorkspaceState
from apps.api.agents.tools import AgentToolContext


def _is_chat_only(state: WorkspaceState) -> bool:
    """自由提问且没有附带文件：走轻量对话链路，不需要证据分析。"""
    intent = state.get("intent", "free")
    has_files = bool(state.get("files"))
    return intent == TaskIntent.FREE.value and not has_files


def _needs_revision(state: WorkspaceState) -> str:
    if state.get("revision_of") == "reviewer":
        return "revise"
    return "confirm"


def _after_organizer(state: WorkspaceState) -> str:
    return "chat_answer" if _is_chat_only(state) else "review"


def _after_coach(state: WorkspaceState) -> str:
    return "chat_finish" if _is_chat_only(state) else "audit"


def build_workspace_graph(tool_ctx: AgentToolContext):
    """用 LangGraph 编排多 Agent 协作。

    两条链路：
    - 附带文件时：整理 → 复盘 → 画像 → 问答 → 审核 →（必要时回复盘）→ 确认闸门。
    - 纯文字自由提问时：整理 → 问答 → 直接完成，不跑证据分析节点，
      让用户像普通聊天一样立即拿到回答。
    """
    graph = StateGraph(WorkspaceState)

    graph.add_node("organizer", partial(organizer_node, tool_ctx=tool_ctx))
    graph.add_node("reviewer", partial(reviewer_node, tool_ctx=tool_ctx))
    graph.add_node("profiler", partial(profiler_node, tool_ctx=tool_ctx))
    graph.add_node("coach", partial(coach_node, tool_ctx=tool_ctx))
    graph.add_node("auditor", partial(auditor_node, tool_ctx=tool_ctx))
    graph.add_node("finish", partial(finish_node, tool_ctx=tool_ctx))
    graph.add_node("chat_finish", partial(finish_node, tool_ctx=tool_ctx, chat_only=True))

    graph.set_entry_point("organizer")
    graph.add_conditional_edges(
        "organizer",
        _after_organizer,
        {"chat_answer": "coach", "review": "reviewer"},
    )
    graph.add_edge("reviewer", "profiler")
    graph.add_edge("profiler", "coach")
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
