from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.agents.tools import AgentToolContext
from apps.api.db.models.profile import ProfileClaim, ProfileSnapshot
from apps.api.gateway.schemas import GatewayOptions, GatewayRequest, ResponseFormat
from apps.api.profile.schemas import ProfileClaimUpsert, ProfileGroup
from apps.api.profile.service import ProfileService, profile_service
from apps.api.review.service import PROFILE_GROUP_LABELS

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "profile_edit" / "v1.txt"
_MAX_ACTIONS = 5


class ProfileEditAction(BaseModel):
    action: Literal["upsert", "delete"]
    group: ProfileGroup
    key: str = Field(min_length=1, max_length=128)
    value: str = Field(default="", max_length=2000)
    claim_id: int = 0


class ProfileEditOutput(BaseModel):
    actions: list[ProfileEditAction] = Field(default_factory=list, max_length=_MAX_ACTIONS)
    summary: str = Field(default="", max_length=200)


PROFILE_EDIT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["actions", "summary"],
    "properties": {
        "actions": {
            "type": "array",
            "maxItems": _MAX_ACTIONS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["action", "group", "key", "value", "claim_id"],
                "properties": {
                    "action": {"type": "string", "enum": ["upsert", "delete"]},
                    "group": {
                        "type": "string",
                        "enum": [item.value for item in ProfileGroup],
                    },
                    "key": {"type": "string", "maxLength": 128},
                    "value": {"type": "string", "maxLength": 2000},
                    "claim_id": {"type": "integer"},
                },
            },
        },
        "summary": {"type": "string", "maxLength": 200},
    },
}


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


async def _ensure_snapshot(
    session: AsyncSession, user_id: int, period: str
) -> None:
    exists = (
        await session.execute(
            select(ProfileSnapshot.id)
            .where(ProfileSnapshot.user_id == user_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if exists is None:
        snapshot = ProfileSnapshot(
            user_id=user_id,
            period=period[:32],
            status="DONE",
            prompt_version="profile-edit-v1",
            created_at=datetime.now(UTC),
        )
        session.add(snapshot)
        await session.flush()


async def _current_claims(
    session: AsyncSession, user_id: int
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(ProfileClaim)
            .where(
                ProfileClaim.user_id == user_id,
                ProfileClaim.is_deleted.is_(False),
            )
            .order_by(ProfileClaim.id.desc())
            .limit(50)
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "方面": PROFILE_GROUP_LABELS.get(row.group_name, row.group_name),
            "group": row.group_name,
            "key": row.claim_key,
            "结论": row.value_text,
        }
        for row in rows
    ]


async def apply_profile_edits(
    tool_ctx: AgentToolContext,
    *,
    message: str,
    supplement: str,
    period: str,
    service: ProfileService = profile_service,
) -> str:
    """把用户自述转成画像编辑操作并落库，返回给用户看的摘要。"""
    session = tool_ctx.session
    if session is None:
        return "现在还没法更新画像，稍后再试一次。"

    await _ensure_snapshot(session, tool_ctx.user_id, period)
    claims = await _current_claims(session, tool_ctx.user_id)
    payload = {
        "用户这句话": message,
        "补充要求": supplement,
        "现有结论": claims,
    }
    request = GatewayRequest(
        task="profile_edit",
        messages=[
            {"role": "system", "content": _load_prompt()},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        options=GatewayOptions(
            response_format=ResponseFormat.JSON_SCHEMA,
            output_schema=PROFILE_EDIT_JSON_SCHEMA,
            max_tokens=600,
            timeout_seconds=15,
        ),
        user_id=tool_ctx.user_id,
    )
    try:
        response = await tool_ctx.model.gateway.complete(
            request, meter=tool_ctx.model.meter
        )
        raw = response.data
        if raw is None and response.content:
            raw = json.loads(response.content)
        output = ProfileEditOutput.model_validate(raw or {})
    except Exception:  # noqa: BLE001 - 解析失败不写库
        return "我没太看懂要改哪一条，你可以直接说「记住我是…」或「把 XX 那条删掉」。"

    applied: list[str] = []
    valid_ids = {int(item["id"]) for item in claims}
    for index, action in enumerate(output.actions[:_MAX_ACTIONS]):
        try:
            if action.action == "upsert":
                if not action.value.strip():
                    continue
                evidence_ids = [
                    int(item["id"])
                    for item in claims
                    if int(item["id"]) in valid_ids and item["key"] == action.key
                ][:3]
                await service.upsert_claim(
                    session,
                    tool_ctx.user_id,
                    ProfileClaimUpsert(
                        group=action.group,
                        key=action.key,
                        value=action.value.strip(),
                        evidence_fragment_ids=evidence_ids,
                    ),
                )
                applied.append(f"已记下「{action.key}」")
            elif action.claim_id in valid_ids:
                await service.delete_claim(session, tool_ctx.user_id, action.claim_id)
                applied.append("已删掉一条旧结论")
        except Exception:  # noqa: BLE001 - 单条失败不影响其他操作
            applied.append("有一条没改成功")
        if index >= _MAX_ACTIONS:
            break

    if not applied:
        return output.summary or "这次没有改动画像，你可以说得更具体一点。"
    return f"已更新画像：{'；'.join(applied)}。"
