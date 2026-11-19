from __future__ import annotations

import re
from datetime import datetime
from email.header import decode_header
from email.parser import Parser
from email.utils import parsedate_to_datetime

from apps.api.ingestion.collectors.base import BaseCollector
from apps.api.ingestion.schemas import RawItem, Role, SourceType, TimePrecision

_DIARY_DATE_RE = re.compile(r"^\s*(?:#{1,6}\s*)?(?P<date>\d{4}-\d{1,2}-\d{1,2})\s*$")
_VOICE_LINE_RE = re.compile(
    r"^\s*\[?(?P<offset>\d{1,2}:\d{2}(?::\d{2})?)\]?\s*"
    r"(?P<speaker>[^:：\[\]]{1,20})[:：]\s*(?P<content>.*)$"
)


def _as_text(payload: str | bytes) -> str:
    return payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload


def _decode_mime(value: str) -> str:
    parts: list[str] = []
    for raw, charset in decode_header(value or ""):
        if isinstance(raw, bytes):
            try:
                parts.append(raw.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                parts.append(raw.decode("utf-8", errors="replace"))
        else:
            parts.append(raw)
    return "".join(parts).strip()


def _parse_email_time(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.replace(tzinfo=None) if parsed else None
    except (TypeError, ValueError, IndexError):
        return None


def _email_body(message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace").strip()
    payload = message.get_payload()
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, bytes):
        charset = message.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace").strip()
    return ""


class EmailCollector(BaseCollector):
    source_type = SourceType.EMAIL

    def collect(self, payload: str | bytes, *, filename: str | None = None) -> list[RawItem]:
        text = _as_text(payload)
        message = Parser().parsestr(text)
        subject = _decode_mime(message.get("Subject", ""))
        sender = _decode_mime(message.get("From", ""))
        timestamp = _parse_email_time(message.get("Date", "") or "")
        body = _email_body(message)
        if not sender and not message.get("Date"):
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines:
                subject = subject or lines[0]
                body = body or "\n".join(lines[1:])
        if not body:
            return []
        content = f"主题：{subject}\n{body}" if subject else body
        return [
            RawItem(
                source_item_id="email-1",
                role=Role.USER,
                content=content,
                timestamp=timestamp,
                time_precision=TimePrecision.HIGH if timestamp else TimePrecision.INFERRED,
                confidence=0.85,
                metadata={"from": sender, "subject": subject, "source": "email"},
            )
        ]


class VoiceCollector(BaseCollector):
    source_type = SourceType.VOICE

    def collect(self, payload: str | bytes, *, filename: str | None = None) -> list[RawItem]:
        text = _as_text(payload)
        items: list[RawItem] = []
        for index, line in enumerate(text.splitlines(), 1):
            match = _VOICE_LINE_RE.match(line)
            if not match:
                continue
            content = match.group("content").strip()
            if not content:
                continue
            items.append(
                RawItem(
                    source_item_id=f"voice-{index}",
                    role=Role.USER,
                    content=content,
                    timestamp=None,
                    time_precision=TimePrecision.LOW,
                    confidence=0.8,
                    metadata={
                        "offset": match.group("offset"),
                        "speaker": match.group("speaker").strip(),
                        "source": "voice",
                    },
                )
            )
        if not items and text.strip():
            items.append(
                RawItem(
                    source_item_id="voice-1",
                    role=Role.USER,
                    content=text.strip(),
                    time_precision=TimePrecision.INFERRED,
                    confidence=0.3,
                    metadata={"fallback": "single_block", "source": "voice"},
                )
            )
        return items


class DiaryCollector(BaseCollector):
    source_type = SourceType.DIARY

    def collect(self, payload: str | bytes, *, filename: str | None = None) -> list[RawItem]:
        text = _as_text(payload)
        blocks: list[tuple[datetime | None, list[str]]] = []
        current: tuple[datetime | None, list[str]] | None = None
        for line in text.splitlines():
            match = _DIARY_DATE_RE.match(line)
            if match:
                if current:
                    blocks.append(current)
                try:
                    stamp: datetime | None = datetime.strptime(match.group("date"), "%Y-%m-%d")
                except ValueError:
                    stamp = None
                current = (stamp, [])
            elif current:
                current[1].append(line)
        if current:
            blocks.append(current)

        items: list[RawItem] = []
        for index, (stamp, lines) in enumerate(blocks, 1):
            content = "\n".join(lines).strip()
            if not content:
                continue
            items.append(
                RawItem(
                    source_item_id=f"diary-{index}",
                    role=Role.USER,
                    content=content,
                    timestamp=stamp,
                    time_precision=TimePrecision.HIGH if stamp else TimePrecision.INFERRED,
                    confidence=0.95,
                    metadata={"source": "diary"},
                )
            )
        if not items and text.strip():
            items.append(
                RawItem(
                    source_item_id="diary-1",
                    role=Role.USER,
                    content=text.strip(),
                    time_precision=TimePrecision.INFERRED,
                    confidence=0.4,
                    metadata={"fallback": "single_block", "source": "diary"},
                )
            )
        return items
