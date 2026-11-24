from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from typing import Any

from apps.api.ingestion.collectors.base import BaseCollector
from apps.api.ingestion.collectors.markdown import MarkdownCollector
from apps.api.ingestion.schemas import RawItem, Role, SourceType, TimePrecision

_ROLE_MAP = {
    "user": Role.USER,
    "human": Role.USER,
    "you": Role.USER,
    "assistant": Role.ASSISTANT,
    "ai": Role.ASSISTANT,
    "model": Role.ASSISTANT,
    "system": Role.SYSTEM,
    "tool": Role.TOOL,
}
_ROLE_KEYS = ("role", "author", "sender", "from")
_CONTENT_KEYS = ("content", "text", "message", "value")
_TIME_KEYS = ("create_time", "created_at", "timestamp", "time", "inserted_at")
# DeepSeek 官方导出把正文放在 fragments 里；THINK 等过程性片段不属于对话正文
_FRAGMENT_CONTENT_TYPES = {"REQUEST", "RESPONSE", "TEXT", "CONTENT"}
_FRAGMENT_SKIP_TYPES = {"THINK", "THINKING", "REASONING", "TOOL", "TOOL_CALL", "SEARCH"}


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, (int, float)) and not isinstance(value, str):
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, tz=datetime.now().astimezone().tzinfo)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _role_of(value: Any) -> Role | None:
    if not isinstance(value, str):
        return None
    return _ROLE_MAP.get(value.strip().lower())


def _content_of(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in _CONTENT_KEYS:
                    if key in item and isinstance(item[key], str):
                        parts.append(item[key])
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        for key in _CONTENT_KEYS:
            if key in value:
                return _content_of(value[key])
    return ""


class DeepSeekArchiveCollector(BaseCollector):
    source_type = SourceType.DEEPSEEK_ARCHIVE

    def collect(self, payload: str | bytes, *, filename: str | None = None) -> list[RawItem]:
        raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        if not zipfile.is_zipfile(io.BytesIO(raw)):
            return MarkdownCollector().collect(raw, filename=filename)

        items: list[RawItem] = []
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in archive.namelist():
                if name.endswith("/"):
                    continue
                content = archive.read(name)
                if name.lower().endswith(".json"):
                    try:
                        data = json.loads(content.decode("utf-8-sig"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    items.extend(self._walk(data, source=f"zip:{name}"))
                elif name.lower().endswith((".md", ".txt")):
                    for item in MarkdownCollector().collect(content, filename=name):
                        item.source_item_id = f"zip:{name}:{item.source_item_id}"
                        items.append(item)
        return items

    def _walk(self, node: Any, *, source: str) -> list[RawItem]:
        items: list[RawItem] = []
        if isinstance(node, list):
            for index, child in enumerate(node):
                items.extend(self._walk(child, source=f"{source}[{index}]"))
            return items
        if not isinstance(node, dict):
            return items

        messages = node.get("messages") or node.get("conversation") or node.get("chat")
        if isinstance(messages, list):
            for index, message in enumerate(messages):
                item = self._message_to_item(message, source=f"{source}:{index}")
                if item:
                    items.append(item)
            return items

        role = next((_role_of(node[key]) for key in _ROLE_KEYS if key in node), None)
        if role:
            item = self._message_to_item(node, source=source)
            if item:
                items.append(item)
            return items

        for key, value in node.items():
            if isinstance(value, (dict, list)) and not re.search(
                "account|user_info|setting|config", key, re.IGNORECASE
            ):
                items.extend(self._walk(value, source=f"{source}.{key}"))
        return items

    def _message_to_item(self, message: Any, *, source: str) -> RawItem | None:
        if not isinstance(message, dict):
            return None
        role = next((_role_of(message[key]) for key in _ROLE_KEYS if key in message), None)
        if role is None:
            return None
        content = _content_of(next((message[key] for key in _CONTENT_KEYS if key in message), ""))
        if not content:
            content = self._fragments_content(message.get("fragments"))
        if not content:
            return None
        raw_time = next((message[key] for key in _TIME_KEYS if key in message), None)
        timestamp = _parse_time(raw_time)
        return RawItem(
            source_item_id=source,
            role=role,
            content=content,
            timestamp=timestamp,
            time_precision=TimePrecision.HIGH if timestamp else TimePrecision.INFERRED,
            confidence=0.9,
            metadata={"source": source},
        )

    @staticmethod
    def _fragments_content(fragments: Any) -> str:
        """兼容 DeepSeek 官方导出：正文在 fragments[].content，按 type 过滤过程性片段。"""
        if not isinstance(fragments, list):
            return ""
        parts: list[str] = []
        for fragment in fragments:
            if not isinstance(fragment, dict):
                continue
            frag_type = str(fragment.get("type") or "").strip().upper()
            if frag_type in _FRAGMENT_SKIP_TYPES:
                continue
            if frag_type and frag_type not in _FRAGMENT_CONTENT_TYPES:
                continue
            text = fragment.get("content")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        return "\n".join(parts).strip()
