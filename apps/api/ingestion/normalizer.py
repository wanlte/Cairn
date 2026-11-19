from __future__ import annotations

import hashlib
import re
from datetime import datetime
from uuid import uuid4

from apps.api.ingestion.schemas import (
    NormalizedConversation,
    NormalizedTurn,
    RawItem,
    Role,
    SourceType,
    TimePrecision,
)

_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_EXPORTED_RE = re.compile(r"\*\*Exported:\*\*\s*(.+)", re.IGNORECASE)


def content_hash(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _parse_exported_time(text: str) -> datetime | None:
    match = _EXPORTED_RE.search(text)
    if not match:
        return None
    try:
        return datetime.fromisoformat(match.group(1).strip())
    except ValueError:
        return None


class Normalizer:
    def normalize(
        self,
        *,
        raw_text: str,
        items: list[RawItem],
        source_type: SourceType,
        source_ref: str,
        single_role: bool = False,
    ) -> NormalizedConversation:
        title_match = _TITLE_RE.search(raw_text)
        title = title_match.group(1).strip() if title_match else source_ref or "untitled"
        captured_at = _parse_exported_time(raw_text)
        anomalies: list[str] = []

        turns: list[NormalizedTurn] = []
        if single_role:
            for item in items:
                if not item.content.strip():
                    anomalies.append(f"空记录：{item.source_item_id}")
                    continue
                timestamp = item.timestamp or captured_at
                precision = (
                    TimePrecision.HIGH
                    if item.timestamp and item.time_precision == TimePrecision.HIGH
                    else TimePrecision.INFERRED
                )
                turns.append(
                    NormalizedTurn(
                        seq=len(turns) + 1,
                        user_content=item.content,
                        assistant_content="",
                        asked_at=timestamp,
                        time_precision=precision,
                        role_confidence=round(item.confidence, 3),
                        content_hash=content_hash(item.content, ""),
                    )
                )
        else:
            pending_users: list[RawItem] = []
            for item in items:
                if item.role == Role.USER:
                    pending_users.append(item)
                    continue
                if item.role != Role.ASSISTANT:
                    anomalies.append(f"跳过非问答角色：{item.source_item_id}")
                    continue

                paired_users = pending_users
                user_content = "\n\n".join(part.content for part in paired_users)
                if paired_users:
                    pending_users = []
                else:
                    anomalies.append(f"助手轮次缺少 preceding 用户消息：{item.source_item_id}")

                if not user_content.strip():
                    anomalies.append(f"空用户轮次：{item.source_item_id}")
                if not item.content.strip():
                    anomalies.append(f"空助手轮次：{item.source_item_id}")

                timestamp = next(
                    (part.timestamp for part in reversed(paired_users) if part.timestamp),
                    None,
                ) or item.timestamp
                precision = (
                    TimePrecision.HIGH
                    if timestamp and item.time_precision == TimePrecision.HIGH
                    else TimePrecision.INFERRED
                )
                if timestamp is None and captured_at:
                    timestamp = captured_at
                    precision = TimePrecision.INFERRED

                confidences = [part.confidence for part in paired_users] + [item.confidence]
                role_confidence = min(confidences) if confidences else 0.0
                turns.append(
                    NormalizedTurn(
                        seq=len(turns) + 1,
                        user_content=user_content,
                        assistant_content=item.content,
                        asked_at=timestamp,
                        time_precision=precision,
                        role_confidence=round(role_confidence, 3),
                        content_hash=content_hash(user_content, item.content),
                    )
                )

            if pending_users:
                anomalies.append("末尾存在未配对的用户消息")

        conversation_hash = content_hash(*(turn.content_hash for turn in turns))
        return NormalizedConversation(
            title=title,
            source_type=source_type,
            source_ref=source_ref,
            raw_text=raw_text,
            items=items,
            turns=turns,
            captured_at=captured_at,
            time_precision=(
                TimePrecision.HIGH if captured_at else TimePrecision.INFERRED
            ),
            content_hash=conversation_hash or content_hash(raw_text),
            anomalies=anomalies,
        )


def new_preview_turn_id() -> str:
    return f"turn-{uuid4().hex[:12]}"
