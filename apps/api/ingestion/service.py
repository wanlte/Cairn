from __future__ import annotations

import base64
import binascii
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models.ingestion import RawConversation, TurnPair
from apps.api.errors import AppError
from apps.api.ingestion.collectors import collector_for
from apps.api.ingestion.normalizer import Normalizer, content_hash, new_preview_turn_id
from apps.api.ingestion.schemas import (
    SINGLE_ROLE_SOURCES,
    IngestCommitRequest,
    IngestionPreview,
    IngestPreviewRequest,
    NormalizedConversation,
    NormalizedTurn,
    PreviewTurn,
    SourceType,
    TurnCorrection,
)

PREVIEW_TTL_SECONDS = 30 * 60
LOW_CONFIDENCE_THRESHOLD = 0.7


class IngestionService:
    def __init__(self) -> None:
        self.normalizer = Normalizer()
        self._previews: dict[
            str, tuple[float, int, IngestionPreview, NormalizedConversation]
        ] = {}

    @staticmethod
    def _decode(request: IngestPreviewRequest) -> tuple[str | bytes, str]:
        if request.source_type == SourceType.DEEPSEEK_ARCHIVE:
            if not request.base64:
                raise AppError("VALIDATION_ERROR", "ZIP 采集需要 base64 字段", 422)
            try:
                return base64.b64decode(request.base64, validate=True), request.filename or "archive.zip"
            except (binascii.Error, ValueError) as exc:
                raise AppError("VALIDATION_ERROR", "base64 解码失败", 422) from exc
        if not request.text:
            raise AppError("VALIDATION_ERROR", "text 字段不能为空", 422)
        return request.text, request.filename or f"{request.source_type.value}-{uuid.uuid4().hex[:8]}"

    def preview(self, user_id: int, request: IngestPreviewRequest) -> IngestionPreview:
        payload, source_ref = self._decode(request)
        collector = collector_for(request.source_type)
        items = collector.collect(payload, filename=source_ref)
        raw_text = (
            payload
            if isinstance(payload, str)
            else "\n".join(
                f"[{item.role or 'unknown'}] {item.content}" for item in items
            )
        )
        conversation = self.normalizer.normalize(
            raw_text=raw_text,
            items=items,
            source_type=request.source_type,
            source_ref=source_ref,
            single_role=request.source_type in SINGLE_ROLE_SOURCES,
        )
        turn_ids = [new_preview_turn_id() for _ in conversation.turns]
        turns = [
            PreviewTurn(
                turn_id=turn_id,
                **turn.model_dump(exclude={"correction"}),
                low_confidence=turn.role_confidence < LOW_CONFIDENCE_THRESHOLD,
            )
            for turn_id, turn in zip(turn_ids, conversation.turns, strict=True)
        ]
        preview = IngestionPreview(
            preview_id=f"preview-{uuid.uuid4().hex}",
            title=conversation.title,
            source_type=conversation.source_type,
            source_ref=conversation.source_ref,
            total_turns=len(turns),
            low_confidence_count=sum(1 for turn in turns if turn.low_confidence),
            anomalies=conversation.anomalies,
            turns=turns,
        )
        self._previews[preview.preview_id] = (
            time.monotonic(),
            user_id,
            preview,
            conversation,
        )
        return preview

    def _get_preview(
        self, user_id: int, preview_id: str
    ) -> tuple[IngestionPreview, NormalizedConversation]:
        entry = self._previews.get(preview_id)
        if not entry:
            raise AppError("PREVIEW_NOT_FOUND", "预览不存在或已过期", 404)
        created_at, owner_id, preview, conversation = entry
        if time.monotonic() - created_at > PREVIEW_TTL_SECONDS:
            self._previews.pop(preview_id, None)
            raise AppError("PREVIEW_NOT_FOUND", "预览已过期", 404)
        if owner_id != user_id:
            raise AppError("PREVIEW_NOT_FOUND", "预览不存在", 404)
        return preview, conversation

    @staticmethod
    def _apply_corrections(
        preview: IngestionPreview,
        conversation: NormalizedConversation,
        corrections: list[TurnCorrection],
    ) -> list[NormalizedTurn]:
        turn_by_id = {turn.turn_id: turn for turn in preview.turns}
        turns = [turn.model_copy(deep=True) for turn in conversation.turns]
        by_seq = {turn.seq: turn for turn in turns}
        for correction in corrections:
            preview_turn = turn_by_id.get(correction.turn_id)
            if not preview_turn:
                raise AppError("VALIDATION_ERROR", f"轮次不存在：{correction.turn_id}", 422)
            turn = by_seq[preview_turn.seq]
            changes = correction.model_dump(exclude={"turn_id"}, exclude_none=True)
            for field in ("user_content", "assistant_content", "asked_at", "time_precision"):
                if field in changes:
                    setattr(turn, field, changes[field])
            turn.correction = changes
            turn.content_hash = content_hash(turn.user_content, turn.assistant_content)
        return turns

    async def commit(
        self, session: AsyncSession, user_id: int, request: IngestCommitRequest
    ) -> dict:
        preview, conversation = self._get_preview(user_id, request.preview_id)
        turns = self._apply_corrections(preview, conversation, request.corrections)

        existing = (
            await session.execute(
                select(RawConversation).where(
                    RawConversation.user_id == user_id,
                    RawConversation.content_hash == conversation.content_hash,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return {
                "conversation_id": existing.id,
                "turn_count": len(turns),
                "duplicate": True,
            }

        record = RawConversation(
            user_id=user_id,
            source_type=conversation.source_type.value,
            source_ref=conversation.source_ref,
            title=conversation.title,
            content_hash=conversation.content_hash,
            raw_text=conversation.raw_text,
            captured_at=conversation.captured_at,
            time_precision=conversation.time_precision.value,
            anomalies_json=conversation.anomalies,
        )
        session.add(record)
        await session.flush()

        for turn in turns:
            session.add(
                TurnPair(
                    user_id=user_id,
                    conversation_id=record.id,
                    seq=turn.seq,
                    user_content=turn.user_content,
                    assistant_content=turn.assistant_content,
                    asked_at=turn.asked_at,
                    time_precision=turn.time_precision.value,
                    role_confidence=turn.role_confidence,
                    content_hash=turn.content_hash,
                    is_corrected=turn.correction is not None,
                    correction_json=turn.correction,
                )
            )
        await session.flush()
        self._previews.pop(request.preview_id, None)
        return {
            "conversation_id": record.id,
            "turn_count": len(turns),
            "duplicate": False,
        }

    async def list_conversations(self, session: AsyncSession, user_id: int) -> list[dict]:
        rows = (
            await session.execute(
                select(RawConversation)
                .where(RawConversation.user_id == user_id)
                .order_by(RawConversation.id.desc())
            )
        ).scalars().all()
        return [
            {
                "id": row.id,
                "title": row.title,
                "source_type": row.source_type,
                "source_ref": row.source_ref,
                "content_hash": row.content_hash,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    async def get_conversation(
        self, session: AsyncSession, user_id: int, conversation_id: int
    ) -> dict:
        conversation = await session.get(RawConversation, conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise AppError("CONVERSATION_NOT_FOUND", "对话不存在", 404)
        turns = (
            await session.execute(
                select(TurnPair)
                .where(TurnPair.conversation_id == conversation_id)
                .order_by(TurnPair.seq)
            )
        ).scalars().all()
        return {
            "id": conversation.id,
            "title": conversation.title,
            "source_type": conversation.source_type,
            "source_ref": conversation.source_ref,
            "anomalies": conversation.anomalies_json,
            "turns": [
                {
                    "id": turn.id,
                    "seq": turn.seq,
                    "user_content": turn.user_content,
                    "assistant_content": turn.assistant_content,
                    "asked_at": turn.asked_at.isoformat() if turn.asked_at else None,
                    "time_precision": turn.time_precision,
                    "role_confidence": float(turn.role_confidence),
                    "is_corrected": turn.is_corrected,
                    "correction": turn.correction_json,
                }
                for turn in turns
            ],
        }


ingestion_service = IngestionService()
