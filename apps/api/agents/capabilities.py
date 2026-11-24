from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field

from apps.api.agents.state import ContextBundle
from apps.api.agents.tools import (
    AgentToolContext,
    FileInput,
    ToolResult,
    coach_context,
    generate_profile,
    generate_review,
    ingest_and_extract,
)
from apps.api.ingestion.web import extract_link_context


class CapabilityArg(BaseModel):
    name: str
    value: str


class CapabilityPlan(BaseModel):
    """LLM 为通用任务选出的能力调用计划。"""

    capability: str
    args: list[CapabilityArg] = Field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class Capability:
    """一个可被通用任务调用的能力。新增能力只需注册一个 handler。"""

    name: str
    description: str
    handler: Callable[..., Awaitable[ToolResult | dict]]

    def arg_text(self, args: list[CapabilityArg]) -> str:
        values = {item.name: item.value for item in args}
        return values.get("text") or values.get("message") or values.get("query") or ""


async def _ingest(
    ctx: AgentToolContext,
    context: ContextBundle,
    args: list[CapabilityArg],
) -> ToolResult:
    files = [FileInput(name=item.get("name", ""), content=item.get("content", "")) for item in context.files]
    if not files:
        return ToolResult(ok=False, message="没有可整理的附件", data={"summary": "这次没有带附件，先聊几句也行。"})
    return await ingest_and_extract(ctx, files)


async def _retrieve(
    ctx: AgentToolContext,
    context: ContextBundle,
    args: list[CapabilityArg],
) -> ToolResult:
    text = Capability("retrieve", "", _retrieve).arg_text(args) or context.user_message
    data = await coach_context(ctx, text)
    records = data.get("相关记录") or []
    return ToolResult(
        ok=True,
        message=f"找到了 {len(records)} 条相关记录",
        data={"summary": f"从过往记录里找到了 {len(records)} 条相关内容。", "records": records},
    )


async def _review(
    ctx: AgentToolContext,
    context: ContextBundle,
    args: list[CapabilityArg],
) -> ToolResult:
    period = Capability("review", "", _review).arg_text(args) or "这次"
    return await generate_review(ctx, context, period)


async def _profile_read(
    ctx: AgentToolContext,
    context: ContextBundle,
    args: list[CapabilityArg],
) -> ToolResult:
    data = await coach_context(ctx, context.user_message)
    claims = data.get("画像") or []
    return ToolResult(
        ok=True,
        message=f"读到 {len(claims)} 条画像结论",
        data={"summary": f"画像里目前记着 {len(claims)} 条结论。", "claims": claims},
    )


async def _profile_write(
    ctx: AgentToolContext,
    context: ContextBundle,
    args: list[CapabilityArg],
) -> ToolResult:
    period = Capability("profile_write", "", _profile_write).arg_text(args) or "这次"
    return await generate_profile(ctx, context, period)


async def _web_fetch(
    ctx: AgentToolContext,
    context: ContextBundle,
    args: list[CapabilityArg],
) -> ToolResult:
    del ctx
    text = Capability("web_fetch", "", _web_fetch).arg_text(args) or context.user_message
    from apps.api.workspace.schemas import WorkspaceTaskCreate

    link_context = await extract_link_context(WorkspaceTaskCreate(message=text))
    if link_context.contents:
        return ToolResult(
            ok=True,
            message="链接内容读到了",
            data={"summary": "已经读到链接正文。", "content": link_context.combined},
        )
    return ToolResult(
        ok=False,
        message="链接没读到内容",
        data={"summary": "；".join(link_context.notices) or "这个链接没能读到正文，麻烦把内容贴进来。"},
    )


REGISTRY: dict[str, Capability] = {
    item.name: item
    for item in [
        Capability(
            name="ingest",
            description="把本次上传的对话文件整理成可检索的结构化碎片",
            handler=_ingest,
        ),
        Capability(
            name="retrieve",
            description="从过往对话记录和画像里找出与当前问题相关的内容",
            handler=_retrieve,
        ),
        Capability(
            name="review",
            description="基于已有对话生成一份结构化复盘报告",
            handler=_review,
        ),
        Capability(
            name="profile_read",
            description="读取当前成长画像里已经记下的结论",
            handler=_profile_read,
        ),
        Capability(
            name="profile_write",
            description="根据已有对话更新成长画像",
            handler=_profile_write,
        ),
        Capability(
            name="web_fetch",
            description="读取消息里分享的网页链接正文",
            handler=_web_fetch,
        ),
    ]
}


def register(capability: Capability) -> None:
    """注册新能力。业务代码无需改动图结构即可获得新工具。"""
    REGISTRY[capability.name] = capability


def capabilities_prompt() -> str:
    return "\n".join(
        f"- {item.name}: {item.description}" for item in REGISTRY.values()
    )
