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
from apps.api.agents.state import WorkspaceState
from apps.api.agents.tools import AgentToolContext


def _needs_revision(state: WorkspaceState) -> str:
    if state.get("revision_of") == "reviewer":
        return "revise"
    return "confirm"


def build_workspace_graph(tool_ctx: AgentToolContext):
    """用 LangGraph 编排多 Agent 协作。

    骨架固定：整理 → 复盘 → 画像 → 问答 → 审核；审核发现证据不足时
    通过条件边回到复盘节点修订一次，随后进入人工确认闸门。
    """
    graph = StateGraph(WorkspaceState)

    graph.add_node("organizer", partial(organizer_node, tool_ctx=tool_ctx))
    graph.add_node("reviewer", partial(reviewer_node, tool_ctx=tool_ctx))
    graph.add_node("profiler", partial(profiler_node, tool_ctx=tool_ctx))
    graph.add_node("coach", partial(coach_node, tool_ctx=tool_ctx))
    graph.add_node("auditor", partial(auditor_node, tool_ctx=tool_ctx))
    graph.add_node("finish", partial(finish_node, tool_ctx=tool_ctx))

    graph.set_entry_point("organizer")
    graph.add_edge("organizer", "reviewer")
    graph.add_edge("reviewer", "profiler")
    graph.add_edge("profiler", "coach")
    graph.add_edge("coach", "auditor")
    graph.add_conditional_edges(
        "auditor",
        _needs_revision,
        {"revise": "reviewer", "confirm": "finish"},
    )
    graph.add_edge("finish", END)

    return graph.compile()
