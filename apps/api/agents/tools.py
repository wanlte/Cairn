from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from apps.api.agents.state import ContextBundle
from apps.api.db.models.extraction import Fragment
from apps.api.errors import AppError
from apps.api.extraction.schemas import ExtractionCreateRequest
from apps.api.extraction.service import extraction_service
from apps.api.gateway.langchain_adapter import GatewayChatModel
from apps.api.ingestion.schemas import IngestCommitRequest, IngestPreviewRequest, SourceType
from apps.api.ingestion.service import ingestion_service
from apps.api.profile.schemas import ProfileGenerateRequest
from apps.api.profile.service import profile_service
from apps.api.review.schemas import ReviewCreateRequest
from apps.api.review.service import PROFILE_GROUP_LABELS, review_service


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
        return ToolResult(
            ok=False,
            message="还没有可复盘的内容",
            data={"review_id": None, "summary": "这次还没有可回看的对话，带上几份对话再来试试。"},
        )
    request = ReviewCreateRequest(
        period=period,
        conversation_id=context.conversation_ids[0] if context.conversation_ids else None,
        direction=context.intent.value,
        supplement=context.supplement or None,
        **_creds(ctx),
    )
    try:
        report = await review_service.create_report(ctx.session, ctx.user_id, request)
    except AppError:
        return ToolResult(
            ok=False,
            message="复盘没能生成，换一个模型再试试",
            data={"review_id": None, "summary": "这次没能整理出复盘，换个模型或再带几份对话试试。"},
        )
    data = {"review_id": report.id, "summary": ""}
    if report.status == "FAILED":
        data["summary"] = "这次复盘没能完整写好，下面还能看到已经记下的部分，也可以换个模型再试一次。"
        return ToolResult(ok=False, message="复盘没能生成，换一个模型再试试", data=data)

    overview = report.overview or {}
    key_events = [item for item in report.items if item.section == "key_event"]
    cognitive = [item for item in report.items if item.section == "cognitive_change"]
    actions = report.action_items

    parts: list[str] = []
    comparison = overview.get("comparison_with_last_period")
    if isinstance(comparison, str) and comparison.strip():
        parts.append(comparison.strip())
    if key_events:
        first = key_events[0].payload or {}
        background = first.get("background") or first.get("my_judgment")
        if background:
            parts.append(f"这次最值得回看的是：{background}")
    if cognitive:
        first_change = cognitive[0].payload or {}
        new_belief = first_change.get("new_belief")
        if new_belief:
            parts.append(f"你的想法有了一个变化：{new_belief}")
    if actions:
        parts.append(f"下一步可以先做：{actions[0].content}")
    data["summary"] = "\n".join(parts) or "这次对话里有一些值得记住的进展。"

    return ToolResult(
        ok=True,
        message="复盘报告写好了",
        data=data,
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


def coach_keywords(message: str, limit: int = 12) -> list[str]:
    """从提问里提取用于匹配历史碎片的短词。"""
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", message or "")
    words = re.findall(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2,}", cleaned)
    terms: list[str] = []
    for word in words:
        if re.fullmatch(r"[\u4e00-\u9fff]+", word):
            terms.extend(word[index : index + 2] for index in range(len(word) - 1))
        else:
            terms.append(word)
    return list(dict.fromkeys(terms))[:limit]


async def coach_context(ctx: AgentToolContext, message: str) -> dict:
    """问答用的画像背景和相关历史碎片。"""
    if ctx.session is None:
        return {"画像": [], "相关记录": []}
    profile_payload: list[dict[str, str]] = []
    try:
        profile = await profile_service.get_current(ctx.session, ctx.user_id)
    except AppError:
        profile = None
    if profile:
        for claim in profile.claims:
            group = getattr(claim.group, "value", str(claim.group))
            profile_payload.append(
                {"方面": PROFILE_GROUP_LABELS.get(group, group), "结论": claim.value}
            )

    rows = (
        await ctx.session.execute(
            select(Fragment)
            .where(Fragment.user_id == ctx.user_id)
            .order_by(Fragment.id.desc())
            .limit(40)
        )
    ).scalars().all()
    terms = coach_keywords(message)
    scored: list[tuple[int, Fragment]] = []
    for row in rows:
        text = json.dumps(row.payload_json or {}, ensure_ascii=False)
        scored.append((sum(1 for term in terms if term in text), row))
    scored.sort(key=lambda item: (-item[0], -item[1].id))
    chosen = [row for score, row in scored[:8] if score > 0] or [
        row for _, row in scored[:5]
    ]
    fragments = [
        {
            "id": row.id,
            "kind": row.kind,
            "payload": json.dumps(row.payload_json or {}, ensure_ascii=False)[:600],
        }
        for row in chosen
    ]
    return {"画像": profile_payload, "相关记录": fragments}
