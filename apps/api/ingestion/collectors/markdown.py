from __future__ import annotations

import re
from uuid import uuid4

from apps.api.ingestion.collectors.base import BaseCollector
from apps.api.ingestion.schemas import RawItem, Role, SourceType, TimePrecision

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_ROLE_WORDS = {
    "you": Role.USER,
    "user": Role.USER,
    "用户": Role.USER,
    "我": Role.USER,
    "assistant": Role.ASSISTANT,
    "助手": Role.ASSISTANT,
    "ai": Role.ASSISTANT,
    "model": Role.ASSISTANT,
}
_INLINE_ROLE_RE = re.compile(r"^\s*(用户|助手|我|AI|You|User|Assistant)\s*[:：]\s*(.+)$", re.IGNORECASE)
_SKIP_RE = re.compile(r"^\[hook:|^\s*---*\s*$", re.IGNORECASE)
_THINKING_RE = re.compile(r"thinking|思考|reasoning|analysis", re.IGNORECASE)


def _clean_heading(value: str) -> str:
    return re.sub(r"[*_`\s]+", " ", value).strip().strip(":").strip()


def _clean_content(value: str) -> str:
    lines = [line for line in value.splitlines() if not _SKIP_RE.match(line)]
    return "\n".join(lines).strip()


def _role_from_heading(heading: str) -> Role | None:
    return _ROLE_WORDS.get(heading.lower())


class MarkdownCollector(BaseCollector):
    source_type = SourceType.MARKDOWN

    def collect(self, payload: str | bytes, *, filename: str | None = None) -> list[RawItem]:
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        items = self._collect_headings(text)
        if not items:
            items = self._collect_inline_roles(text)
        if not items:
            items = [
                RawItem(
                    source_item_id=f"md-{uuid4().hex[:12]}",
                    role=Role.USER,
                    content=_clean_content(text),
                    time_precision=TimePrecision.INFERRED,
                    confidence=0.25,
                    metadata={"fallback": "single_block"},
                )
            ]
        return items

    def _collect_headings(self, text: str) -> list[RawItem]:
        matches = list(_HEADING_RE.finditer(text))
        items: list[RawItem] = []
        for index, match in enumerate(matches):
            heading = _clean_heading(match.group(2))
            if _THINKING_RE.search(heading):
                continue
            role = _role_from_heading(heading)
            if role is None:
                continue
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            content = _clean_content(text[match.end() : end])
            if not content:
                continue
            items.append(
                RawItem(
                    source_item_id=f"md-{index + 1}",
                    role=role,
                    content=content,
                    time_precision=TimePrecision.INFERRED,
                    confidence=0.95,
                    metadata={"heading": heading},
                )
            )
        return items

    def _collect_inline_roles(self, text: str) -> list[RawItem]:
        items: list[RawItem] = []
        current_role: Role | None = None
        buffer: list[str] = []
        index = 0

        def flush() -> None:
            nonlocal buffer
            content = _clean_content("\n".join(buffer))
            if current_role and content:
                items.append(
                    RawItem(
                        source_item_id=f"md-inline-{len(items) + 1}",
                        role=current_role,
                        content=content,
                        time_precision=TimePrecision.INFERRED,
                        confidence=0.6,
                        metadata={"strategy": "inline_role"},
                    )
                )
            buffer = []

        for line in text.splitlines():
            match = _INLINE_ROLE_RE.match(line)
            if match:
                flush()
                token = match.group(1).lower()
                current_role = _ROLE_WORDS.get(token, Role.USER)
                buffer = [match.group(2)]
                index += 1
            elif current_role:
                buffer.append(line)
        flush()
        return items
