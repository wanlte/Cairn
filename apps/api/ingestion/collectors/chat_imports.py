from __future__ import annotations

import re
from datetime import datetime

from apps.api.ingestion.collectors.base import BaseCollector
from apps.api.ingestion.schemas import RawItem, Role, SourceType, TimePrecision

_SELF_TOKENS = {"我", "me", "self", "自己"}
_WECHAT_HEADER_RE = re.compile(
    r"^\s*(?P<sender>[^\s].{0,39}?)\s+"
    r"(?P<time>\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s*$"
)
_FEISHU_LINE_RE = re.compile(
    r"^\s*\[?(?P<time>\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?)\]?\s*"
    r"(?P<sender>[^:：\[\]]{1,40})[:：]\s*(?P<content>.*)$"
)


def _as_text(payload: str | bytes) -> str:
    return payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload


def _parse_datetime(value: str) -> datetime | None:
    text = value.strip().replace("/", "-").replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _is_self(sender: str) -> bool:
    clean = sender.strip().lower()
    return clean in _SELF_TOKENS or clean.endswith(("(我)", "（我）"))


class WechatCollector(BaseCollector):
    source_type = SourceType.WECHAT

    def collect(self, payload: str | bytes, *, filename: str | None = None) -> list[RawItem]:
        text = _as_text(payload)
        blocks: list[tuple[str, str, list[str]]] = []
        current: tuple[str, str, list[str]] | None = None
        for line in text.splitlines():
            match = _WECHAT_HEADER_RE.match(line)
            if match:
                if current:
                    blocks.append((current[0], current[1], current[2]))
                current = (match.group("sender"), match.group("time"), [])
            elif current:
                current[2].append(line)
        if current:
            blocks.append((current[0], current[1], current[2]))

        items: list[RawItem] = []
        for index, (sender, time_text, lines) in enumerate(blocks, 1):
            content = "\n".join(lines).strip()
            if not content:
                continue
            timestamp = _parse_datetime(time_text)
            items.append(
                RawItem(
                    source_item_id=f"wechat-{index}",
                    role=Role.USER if _is_self(sender) else Role.ASSISTANT,
                    content=content,
                    timestamp=timestamp,
                    time_precision=TimePrecision.HIGH if timestamp else TimePrecision.LOW,
                    confidence=0.9,
                    metadata={"sender": sender.strip(), "source": "wechat"},
                )
            )
        return items


class FeishuCollector(BaseCollector):
    source_type = SourceType.FEISHU

    def collect(self, payload: str | bytes, *, filename: str | None = None) -> list[RawItem]:
        text = _as_text(payload)
        items: list[RawItem] = []
        current: RawItem | None = None
        for line in text.splitlines():
            match = _FEISHU_LINE_RE.match(line)
            if match:
                if current and current.content.strip():
                    items.append(current)
                timestamp = _parse_datetime(match.group("time"))
                sender = match.group("sender").strip()
                current = RawItem(
                    source_item_id=f"feishu-{len(items) + 1}",
                    role=Role.USER if _is_self(sender) else Role.ASSISTANT,
                    content=match.group("content").strip(),
                    timestamp=timestamp,
                    time_precision=TimePrecision.HIGH if timestamp else TimePrecision.LOW,
                    confidence=0.9,
                    metadata={"sender": sender, "source": "feishu"},
                )
            elif current and line.strip():
                current.content = f"{current.content}\n{line.strip()}"
        if current and current.content.strip():
            items.append(current)
        return items
