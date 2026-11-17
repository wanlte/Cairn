from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from apps.api.config import get_settings
from apps.api.db.models.extraction import ExtractionRun, Fragment
from apps.api.db.models.ingestion import RawConversation, TurnPair
from apps.api.errors import AppError
from apps.api.extraction.schemas import (
    FRAGMENT_JSON_SCHEMA,
    ExtractionCreateRequest,
    ExtractionOutput,
    ExtractionRunResponse,
    FragmentKind,
    FragmentResponse,
)
from apps.api.gateway.factory import build_gateway_for_user
from apps.api.gateway.schemas import (
    GatewayErrorCode,
    GatewayOptions,
    GatewayRequest,
    ResponseFormat,
    UnifiedError,
)
from apps.api.ingestion.normalizer import content_hash

PROMPT_VERSION = "extraction-v1"
_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "extraction" / "v1.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _error_info(exc: Exception) -> dict[str, str]:
    code = getattr(exc, "code", None)
    if hasattr(code, "value"):
        code = code.value
    return {"code": str(code or exc.__class__.__name__), "message": str(exc)[:300]}


def _canonical_hash(kind: str, payload: dict[str, Any]) -> str:
    excluded = {"occurred_count"}
    if kind == FragmentKind.KNOWLEDGE.value:
        excluded.add("source_turn_id")
    stable = {key: value for key, value in payload.items() if key not in excluded}
    return content_hash(kind, json.dumps(stable, sort_keys=True, ensure_ascii=False))


class ExtractionService:
    async def start(
        self,
        session: AsyncSession,
        user_id: int,
        request: ExtractionCreateRequest,
    ) -> ExtractionRunResponse:
        if request.idempotency_key:
            existing = (
                await session.execute(
                    select(ExtractionRun).where(
                        ExtractionRun.user_id == user_id,
                        ExtractionRun.idempotency_key == request.idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return self.run_to_response(existing)

        conversation = await session.get(RawConversation, request.conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise AppError("CONVERSATION_NOT_FOUND", "对话不存在", 404, retryable=False)

        turn_stmt = (
            select(TurnPair)
            .where(
                TurnPair.user_id == user_id,
                TurnPair.conversation_id == request.conversation_id,
            )
            .order_by(TurnPair.seq)
        )
        if request.max_turns:
            turn_stmt = turn_stmt.limit(request.max_turns)
        turns = (await session.execute(turn_stmt)).scalars().all()
        if not turns:
            raise AppError("TURN_PAIR_EMPTY", "对话没有可抽取轮次", 422)

        gateway, _credential_id, model, provider = await build_gateway_for_user(
            session,
            user_id,
            credential_id=request.credential_id,
            provider=request.provider,
            model=request.model,
        )

        run = ExtractionRun(
            user_id=user_id,
            conversation_id=request.conversation_id,
            status="RUNNING",
            total=len(turns),
            processed=0,
            failed=0,
            prompt_version=PROMPT_VERSION,
            model=model,
            provider=provider.value if provider else None,
            idempotency_key=request.idempotency_key,
            error_json=[],
        )
        session.add(run)
        await session.flush()

        errors: list[dict[str, str]] = []
        settings = get_settings()
        prompt = _load_prompt()

        for turn in turns:
            try:
                output = await self._extract_turn(
                    gateway=gateway,
                    turn=turn,
                    user_id=user_id,
                    run_id=run.id,
                    prompt=prompt,
                    timeout=settings.gateway_read_timeout_review,
                )
                await self._persist_fragments(session, user_id, run.id, turn.id, output)
                run.processed += 1
            except Exception as exc:  # noqa: BLE001 - 单轮失败不能阻断整批
                run.failed += 1
                errors.append({"turn_pair_id": str(turn.id), **_error_info(exc)})
            await session.flush()

        run.error_json = errors
        run.status = "FAILED" if errors else "DONE"
        run.finished_at = datetime.now(UTC)
        await session.flush()
        return self.run_to_response(run)

    async def _extract_turn(
        self,
        *,
        gateway,
        turn: TurnPair,
        user_id: int,
        run_id: int,
        prompt: str,
        timeout: float,
    ) -> ExtractionOutput:
        user_payload = json.dumps(
            {
                "turn_pair_id": turn.id,
                "user": turn.user_content,
                "assistant": turn.assistant_content,
            },
            ensure_ascii=False,
        )
        request = GatewayRequest(
            task="extract",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_payload},
            ],
            options=GatewayOptions(
                response_format=ResponseFormat.JSON_SCHEMA,
                output_schema=FRAGMENT_JSON_SCHEMA,
                timeout_seconds=timeout,
                idempotency_key=f"extract:{run_id}:{turn.id}",
            ),
            user_id=user_id,
        )
        response = await gateway.complete(request)
        if not response.data:
            raise UnifiedError(
                GatewayErrorCode.INVALID_OUTPUT, "抽取结果为空", retryable=False
            )
        return ExtractionOutput.model_validate(response.data)

    async def _persist_fragments(
        self,
        session: AsyncSession,
        user_id: int,
        run_id: int,
        turn_id: int,
        output: ExtractionOutput,
    ) -> None:
        candidates: list[tuple[FragmentKind, dict[str, Any]]] = []
        for event in output.events:
            candidates.append(
                (
                    FragmentKind.EVENT,
                    {"source_turn_id": turn_id, **event.model_dump(mode="json")},
                )
            )
        for knowledge in output.knowledge:
            candidates.append(
                (
                    FragmentKind.KNOWLEDGE,
                    {"source_turn_id": turn_id, **knowledge.model_dump(mode="json")},
                )
            )
        for trait in output.traits:
            candidates.append(
                (
                    FragmentKind.TRAIT,
                    {"source_turn_id": turn_id, **trait.model_dump(mode="json")},
                )
            )
        candidates.append(
            (
                FragmentKind.STATE,
                {"source_turn_id": turn_id, **output.state.model_dump(mode="json")},
            )
        )

        for kind, payload in candidates:
            digest = _canonical_hash(kind.value, payload)
            existing = (
                await session.execute(
                    select(Fragment).where(
                        Fragment.user_id == user_id,
                        Fragment.content_hash == digest,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                if kind == FragmentKind.KNOWLEDGE:
                    existing.payload_json["occurred_count"] = (
                        int(existing.payload_json.get("occurred_count", 1)) + 1
                    )
                    flag_modified(existing, "payload_json")
                continue
            session.add(
                Fragment(
                    user_id=user_id,
                    run_id=run_id,
                    conversation_id=(
                        await session.get(TurnPair, turn_id)
                    ).conversation_id,
                    turn_pair_id=turn_id,
                    kind=kind.value,
                    payload_json=payload,
                    content_hash=digest,
                )
            )

    @staticmethod
    def run_to_response(run: ExtractionRun) -> ExtractionRunResponse:
        return ExtractionRunResponse(
            id=run.id,
            conversation_id=run.conversation_id,
            status=run.status,
            total=run.total,
            processed=run.processed,
            failed=run.failed,
            prompt_version=run.prompt_version,
            model=run.model,
            provider=run.provider,
            error_json=run.error_json or [],
            created_at=run.created_at,
            finished_at=run.finished_at,
        )

    async def list_runs(
        self, session: AsyncSession, user_id: int, limit: int = 50
    ) -> list[ExtractionRunResponse]:
        rows = (
            await session.execute(
                select(ExtractionRun)
                .where(ExtractionRun.user_id == user_id)
                .order_by(ExtractionRun.id.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [self.run_to_response(row) for row in rows]

    async def get_run(
        self, session: AsyncSession, user_id: int, run_id: int
    ) -> ExtractionRunResponse:
        run = await session.get(ExtractionRun, run_id)
        if not run or run.user_id != user_id:
            raise AppError("EXTRACTION_RUN_NOT_FOUND", "抽取任务不存在", 404)
        return self.run_to_response(run)

    async def list_fragments(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        run_id: int | None = None,
        kind: FragmentKind | None = None,
        limit: int = 200,
    ) -> list[FragmentResponse]:
        stmt = select(Fragment).where(Fragment.user_id == user_id)
        if run_id:
            stmt = stmt.where(Fragment.run_id == run_id)
        if kind:
            stmt = stmt.where(Fragment.kind == kind.value)
        rows = (await session.execute(stmt.order_by(Fragment.id).limit(limit))).scalars().all()
        return [
            FragmentResponse(
                id=row.id,
                kind=FragmentKind(row.kind),
                turn_pair_id=row.turn_pair_id,
                payload=row.payload_json,
                content_hash=row.content_hash,
                created_at=row.created_at,
            )
            for row in rows
        ]


extraction_service = ExtractionService()
