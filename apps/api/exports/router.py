from __future__ import annotations

import html
import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.errors import AppError
from apps.api.exports.schemas import ExportResponse
from apps.api.planning.service import planning_service
from apps.api.profile.service import profile_service
from apps.api.review.service import review_service

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])

_TITLES = {"profile": "成长画像", "review": "复盘报告", "plan": "行动规划"}


def _markdown(data: dict[str, Any], depth: int = 1) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{'#' * min(6, depth)} {key}")
            lines.append(_markdown(value, depth + 1))
        elif isinstance(value, list):
            lines.append(f"{'#' * min(6, depth)} {key}")
            for item in value:
                if isinstance(item, dict):
                    lines.append(_markdown(item, depth + 1))
                    lines.append("---")
                else:
                    lines.append(f"- {item}")
        else:
            lines.append(f"- **{key}**：{value}")
    return "\n".join(line for line in lines if line)


async def _load(session: AsyncSession, user_id: int, kind: str) -> dict[str, Any]:
    if kind == "profile":
        return (await profile_service.get_current(session, user_id)).model_dump(mode="json")
    if kind == "review":
        return (await review_service.latest_report(session, user_id)).model_dump(mode="json")
    if kind == "plan":
        return (await planning_service.get_current(session, user_id)).model_dump(mode="json")
    raise AppError("EXPORT_KIND_INVALID", "不知道要导出什么", 400, retryable=False)


@router.get("/{kind}", response_model=ExportResponse)
async def export_data(
    kind: str,
    format: str = Query(default="json", pattern="^(json|md|html)$"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ExportResponse:
    if kind not in _TITLES:
        raise AppError("EXPORT_KIND_INVALID", "不知道要导出什么", 400, retryable=False)
    data = await _load(session, current_user.id, kind)
    title = _TITLES[kind]

    if format == "json":
        content = json.dumps(data, ensure_ascii=False, indent=2)
    elif format == "md":
        content = f"# {title}\n\n{_markdown(data)}"
    else:
        printable = json.dumps(data, ensure_ascii=False, indent=2)
        content = (
            "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
            f"<title>{html.escape(title)}</title>"
            "<style>body{font-family:'PingFang SC',sans-serif;max-width:760px;margin:40px auto;line-height:1.7;color:#172033}"
            "pre{white-space:pre-wrap;font-size:13px}</style></head><body>"
            f"<h1>{html.escape(title)}</h1><pre>{html.escape(printable)}</pre></body></html>"
        )
    return ExportResponse(
        kind=kind,
        format=format,
        filename=f"cairn-{kind}.{('md' if format == 'md' else 'html' if format == 'html' else 'json')}",
        content=content,
    )
