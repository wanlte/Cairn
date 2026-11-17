from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.api.agents.state import ContextBundle
from apps.api.extraction.schemas import ExtractionCreateRequest
from apps.api.extraction.service import extraction_service
from apps.api.gateway.langchain_adapter import GatewayChatModel
from apps.api.ingestion.schemas import IngestCommitRequest, IngestPreviewRequest, SourceType
from apps.api.ingestion.service import ingestion_service
from apps.api.profile.schemas import ProfileGenerateRequest
from apps.api.profile.service import profile_service
from apps.api.review.schemas import ReviewCreateRequest
from apps.api.review.service import review_service


class FileInput(BaseModel):
    name: str
    content: str


class AgentToolContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session: Any
    user_id: int
    credential: dict
    model: GatewayChatModel


class ToolResult(BaseModel):
    ok: bool
    message: str = ""
    data: dict = Field(default_factory=dict)


def _creds(ctx: AgentToolContext) -> dict:
    return dict(ctx.credential)


async def ingest_and_extract(ctx: AgentToolContext, files: list[FileInput]) -> ToolResult:
    """整理师工具：解析对话文件并抽取结构化碎片。"""
    conversation_ids: list[int] = []
    total_turns = 0
    fragment_count = 0
    for file in files:
        is_zip = file.name.lower().endswith(".zip")
        source_type = SourceType.DEEPSEEK_ARCHIVE if is_zip else SourceType.MARKDOWN
        preview_request = IngestPreviewRequest(
            source_type=source_type,
            text=None if is_zip else file.content,
            base64=file.content if is_zip else None,
            filename=file.name,
        )
        preview = ingestion_service.preview(ctx.user_id, preview_request)
        committed = await ingestion_service.commit(
            ctx.session, ctx.user_id, IngestCommitRequest(preview_id=preview.preview_id)
        )
        conv_id = committed["conversation_id"]
        conversation_ids.append(conv_id)
        total_turns += committed["turn_count"]
        run = await extraction_service.start(
            ctx.session,
            ctx.user_id,
            ExtractionCreateRequest(conversation_id=conv_id, **_creds(ctx)),
        )
        if run.status == "FAILED":
            return ToolResult(ok=False, message="内容没能整理完成，请稍后再试")
        fragment_count += run.processed

    if not conversation_ids:
        return ToolResult(ok=False, message="没有识别到可用的对话内容")
    return ToolResult(
        ok=True,
        message=f"整理好了 {len(conversation_ids)} 份对话",
        data={
            "conversation_ids": conversation_ids,
            "turn_count": total_turns,
            "fragment_count": fragment_count,
        },
    )


async def generate_review(
    ctx: AgentToolContext,
    context: ContextBundle,
    period: str,
) -> ToolResult:
    """复盘师工具：基于碎片生成复盘报告。"""
    if context.fragment_count <= 0 and not context.conversation_ids:
        return ToolResult(ok=False, message="还没有可复盘的内容")
    request = ReviewCreateRequest(
        period=period,
        conversation_id=context.conversation_ids[0] if context.conversation_ids else None,
        direction=context.intent.value,
        supplement=context.supplement or None,
        **_creds(ctx),
    )
    report = await review_service.create_report(ctx.session, ctx.user_id, request)
    if report.status == "FAILED":
        return ToolResult(ok=False, message="复盘没能生成，换一个模型再试试")
    overview = report.overview or {}
    lines: list[str] = []
    for value in overview.values():
        if isinstance(value, str) and value.strip():
            lines.append(value.strip())
        elif isinstance(value, dict):
            for nested in value.values():
                if isinstance(nested, str) and nested.strip():
                    lines.append(nested.strip())
    summary = "\n".join(lines[:6]) or "这次对话里有一些值得记住的进展。"
    return ToolResult(
        ok=True,
        message="复盘报告写好了",
        data={"review_id": report.id, "summary": summary},
    )


async def generate_profile(ctx: AgentToolContext, context: ContextBundle, period: str) -> ToolResult:
    """画像师工具：增量更新成长画像。"""
    if context.fragment_count <= 0 and not context.conversation_ids:
        return ToolResult(ok=False, message="还没有可用于画像的内容")
    request = ProfileGenerateRequest(
        period=period,
        conversation_id=context.conversation_ids[0] if context.conversation_ids else None,
        supplement=context.supplement or None,
        **_creds(ctx),
    )
    snapshot = await profile_service.generate(ctx.session, ctx.user_id, request)
    if snapshot.status == "FAILED":
        return ToolResult(ok=False, message="画像没能更新，换一个模型再试试")
    claims = [claim.value for claim in snapshot.claims if claim.value]
    summary = "；".join(claims[:3]) or "这次先记下几笔，下次会更清楚。"
    return ToolResult(
        ok=True,
        message="画像已经更新",
        data={"profile_id": snapshot.id, "summary": summary},
    )
