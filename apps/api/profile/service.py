from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from apps.api.config import get_settings
from apps.api.db.models.extraction import Fragment
from apps.api.db.models.profile import ProfileClaim, ProfileSnapshot
from apps.api.errors import AppError
from apps.api.gateway.factory import build_gateway_for_user
from apps.api.gateway.schemas import GatewayOptions, GatewayRequest, ResponseFormat
from apps.api.profile.schemas import (
    PROFILE_JSON_SCHEMA,
    ClaimSource,
    ProfileClaimResponse,
    ProfileClaimUpsert,
    ProfileDiffResponse,
    ProfileGenerateRequest,
    ProfileGroup,
    ProfileOutput,
    ProfileSnapshotResponse,
)

PROMPT_VERSION = "profile-v1"
_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "profile" / "v1.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if hasattr(code, "value"):
        return str(code.value)
    if isinstance(exc, AppError):
        return exc.code
    return exc.__class__.__name__


class ProfileService:
    async def generate(
        self,
        session: AsyncSession,
        user_id: int,
        request: ProfileGenerateRequest,
    ) -> ProfileSnapshotResponse:
        if request.idempotency_key:
            existing = (
                await session.execute(
                    select(ProfileSnapshot).where(
                        ProfileSnapshot.user_id == user_id,
                        ProfileSnapshot.idempotency_key == request.idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return await self._to_response(session, existing)

        existing_period = (
            await session.execute(
                select(ProfileSnapshot).where(
                    ProfileSnapshot.user_id == user_id,
                    ProfileSnapshot.period == request.period,
                )
            )
        ).scalar_one_or_none()
        if existing_period:
            raise AppError("PROFILE_PERIOD_EXISTS", "该周期画像已存在", 409)

        stmt = select(Fragment).where(Fragment.user_id == user_id)
        if request.conversation_id is not None:
            stmt = stmt.where(Fragment.conversation_id == request.conversation_id)
        fragments = (
            await session.execute(stmt.order_by(Fragment.id.desc()).limit(request.fragment_limit))
        ).scalars().all()
        if not fragments:
            raise AppError("FRAGMENT_EMPTY", "没有可用于画像的碎片", 422)

        previous = (
            await session.execute(
                select(ProfileSnapshot)
                .where(ProfileSnapshot.user_id == user_id)
                .order_by(ProfileSnapshot.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        prior_claims = []
        if previous:
            prior_claims = (
                await session.execute(
                    select(ProfileClaim).where(
                        ProfileClaim.snapshot_id == previous.id,
                        ProfileClaim.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
        rejected = (
            await session.execute(
                select(ProfileClaim).where(
                    ProfileClaim.user_id == user_id,
                    ProfileClaim.is_deleted.is_(True),
                )
            )
        ).scalars().all()

        gateway, _credential_id, model, provider = await build_gateway_for_user(
            session,
            user_id,
            **request.gateway_kwargs(),
        )
        snapshot = ProfileSnapshot(
            user_id=user_id,
            period=request.period,
            status="RUNNING",
            previous_snapshot_id=previous.id if previous else None,
            prompt_version=PROMPT_VERSION,
            model=model,
            provider=provider.value if provider else None,
            idempotency_key=request.idempotency_key,
        )
        session.add(snapshot)
        await session.flush()

        settings = get_settings()
        payload = {
            "period": request.period,
            "fragments": [
                {"id": item.id, "kind": item.kind, "payload": item.payload_json}
                for item in fragments
            ],
            "previous_claims": [
                {
                    "group": item.group_name,
                    "key": item.claim_key,
                    "value": item.value_text,
                    "user_corrected": item.user_corrected,
                }
                for item in prior_claims
            ],
            "rejected_claims": [
                {
                    "group": item.group_name,
                    "key": item.claim_key,
                    "value": item.value_text,
                }
                for item in rejected
            ],
        }
        if request.supplement:
            payload["supplement"] = request.supplement
        gateway_request = GatewayRequest(
            task="profile",
            messages=[
                {"role": "system", "content": _load_prompt()},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            options=GatewayOptions(
                response_format=ResponseFormat.JSON_SCHEMA,
                output_schema=PROFILE_JSON_SCHEMA,
                timeout_seconds=settings.gateway_read_timeout_review,
            ),
            user_id=user_id,
        )

        try:
            response = await gateway.complete(gateway_request)
            if not response.data:
                raise AppError("INVALID_PROFILE_OUTPUT", "画像输出为空", 502)
            output = ProfileOutput.model_validate(response.data)
        except Exception as exc:  # noqa: BLE001 - 失败必须落库
            snapshot.status = "FAILED"
            snapshot.error_code = _error_code(exc)
            await session.flush()
            return await self._to_response(session, snapshot)

        valid_ids = {item.id for item in fragments}
        output = self._enforce_evidence(output, valid_ids)
        rejected_keys = {(item.group_name, item.claim_key) for item in rejected}
        rejected_values = {item.value_text for item in rejected}
        user_corrected_keys = {
            (item.group_name, item.claim_key)
            for item in prior_claims
            if item.user_corrected
        }

        model_claims = self._flatten_output(output)
        for group, key, value, evidence in model_claims:
            if (group.value, key) in rejected_keys or value in rejected_values:
                continue
            if (group.value, key) in user_corrected_keys:
                continue
            session.add(
                ProfileClaim(
                    user_id=user_id,
                    snapshot_id=snapshot.id,
                    group_name=group.value,
                    claim_key=key,
                    value_text=value,
                    evidence_fragment_ids=evidence,
                    source=ClaimSource.MODEL.value,
                )
            )

        for item in prior_claims:
            if not item.user_corrected:
                continue
            session.add(
                ProfileClaim(
                    user_id=user_id,
                    snapshot_id=snapshot.id,
                    group_name=item.group_name,
                    claim_key=item.claim_key,
                    value_text=item.value_text,
                    evidence_fragment_ids=item.evidence_fragment_ids,
                    source=ClaimSource.USER.value,
                    user_corrected=True,
                )
            )

        snapshot.status = "DONE"
        await session.flush()
        return await self._to_response(session, snapshot)

    @staticmethod
    def _enforce_evidence(output: ProfileOutput, valid_ids: set[int]) -> ProfileOutput:
        def clean(ids: list[int]) -> list[int]:
            return [value for value in ids if value in valid_ids][:3]

        output.identity_background = [
            item for item in output.identity_background if clean(item.evidence_fragment_ids)
        ]
        for item in output.identity_background:
            item.evidence_fragment_ids = clean(item.evidence_fragment_ids)
        output.cognitive_style = [
            item for item in output.cognitive_style if clean(item.evidence_fragment_ids)
        ]
        for item in output.cognitive_style:
            item.evidence_fragment_ids = clean(item.evidence_fragment_ids)
        output.attention_trajectory = [
            item for item in output.attention_trajectory if clean(item.evidence_fragment_ids)
        ]
        for item in output.attention_trajectory:
            item.evidence_fragment_ids = clean(item.evidence_fragment_ids)
        output.high_frequency_pitfalls = [
            item
            for item in output.high_frequency_pitfalls
            if clean(item.evidence_fragment_ids)
        ]
        for item in output.high_frequency_pitfalls:
            item.evidence_fragment_ids = clean(item.evidence_fragment_ids)
        output.growth_signals = [
            item for item in output.growth_signals if clean(item.evidence_fragment_ids)
        ]
        for item in output.growth_signals:
            item.evidence_fragment_ids = clean(item.evidence_fragment_ids)
        return output

    @staticmethod
    def _flatten_output(output: ProfileOutput) -> list[tuple[ProfileGroup, str, str, list[int]]]:
        claims: list[tuple[ProfileGroup, str, str, list[int]]] = []
        for item in output.identity_background:
            claims.append((ProfileGroup.IDENTITY_BACKGROUND, item.key, item.value, item.evidence_fragment_ids))
        for item in output.cognitive_style:
            claims.append((ProfileGroup.COGNITIVE_STYLE, item.key, item.value, item.evidence_fragment_ids))
        for item in output.attention_trajectory:
            claims.append(
                (
                    ProfileGroup.ATTENTION_TRAJECTORY,
                    item.domain,
                    f"count={item.count}",
                    item.evidence_fragment_ids,
                )
            )
        for item in output.high_frequency_pitfalls:
            claims.append(
                (
                    ProfileGroup.HIGH_FREQUENCY_PITFALLS,
                    item.pitfall,
                    f"count={item.count}",
                    item.evidence_fragment_ids,
                )
            )
        for item in output.growth_signals:
            claims.append((ProfileGroup.GROWTH_SIGNALS, item.signal, item.value, item.evidence_fragment_ids))
        return claims

    async def _to_response(
        self, session: AsyncSession, snapshot: ProfileSnapshot
    ) -> ProfileSnapshotResponse:
        claims = (
            await session.execute(
                select(ProfileClaim)
                .where(
                    ProfileClaim.snapshot_id == snapshot.id,
                    ProfileClaim.is_deleted.is_(False),
                )
                .order_by(ProfileClaim.id)
            )
        ).scalars().all()
        return ProfileSnapshotResponse(
            id=snapshot.id,
            user_id=snapshot.user_id,
            period=snapshot.period,
            status=snapshot.status,
            previous_snapshot_id=snapshot.previous_snapshot_id,
            prompt_version=snapshot.prompt_version,
            model=snapshot.model,
            provider=snapshot.provider,
            error_code=snapshot.error_code,
            created_at=snapshot.created_at,
            claims=[self._claim_to_response(item) for item in claims],
        )

    @staticmethod
    def _claim_to_response(claim: ProfileClaim) -> ProfileClaimResponse:
        return ProfileClaimResponse(
            id=claim.id,
            group=ProfileGroup(claim.group_name),
            key=claim.claim_key,
            value=claim.value_text,
            evidence_fragment_ids=claim.evidence_fragment_ids,
            source=ClaimSource(claim.source),
            user_corrected=claim.user_corrected,
            is_deleted=claim.is_deleted,
            created_at=claim.created_at,
        )

    async def _current_snapshot(
        self, session: AsyncSession, user_id: int
    ) -> ProfileSnapshot:
        snapshot = (
            await session.execute(
                select(ProfileSnapshot)
                .where(ProfileSnapshot.user_id == user_id)
                .order_by(ProfileSnapshot.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not snapshot:
            raise AppError("PROFILE_NOT_FOUND", "画像不存在", 404)
        return snapshot

    async def get_current(
        self, session: AsyncSession, user_id: int
    ) -> ProfileSnapshotResponse:
        return await self._to_response(session, await self._current_snapshot(session, user_id))

    async def get_by_period(
        self, session: AsyncSession, user_id: int, period: str
    ) -> ProfileSnapshotResponse:
        snapshot = (
            await session.execute(
                select(ProfileSnapshot).where(
                    ProfileSnapshot.user_id == user_id,
                    ProfileSnapshot.period == period,
                )
            )
        ).scalar_one_or_none()
        if not snapshot:
            raise AppError("PROFILE_NOT_FOUND", "画像不存在", 404)
        return await self._to_response(session, snapshot)

    async def list_snapshots(
        self, session: AsyncSession, user_id: int, limit: int = 50
    ) -> list[ProfileSnapshotResponse]:
        snapshots = (
            await session.execute(
                select(ProfileSnapshot)
                .where(ProfileSnapshot.user_id == user_id)
                .order_by(ProfileSnapshot.id.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [await self._to_response(session, item) for item in snapshots]

    async def upsert_claim(
        self,
        session: AsyncSession,
        user_id: int,
        request: ProfileClaimUpsert,
    ) -> ProfileClaimResponse:
        snapshot = await self._current_snapshot(session, user_id)
        claim = (
            await session.execute(
                select(ProfileClaim).where(
                    ProfileClaim.snapshot_id == snapshot.id,
                    ProfileClaim.group_name == request.group.value,
                    ProfileClaim.claim_key == request.key,
                    ProfileClaim.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if claim:
            claim.value_text = request.value
            claim.evidence_fragment_ids = request.evidence_fragment_ids
            claim.source = ClaimSource.USER.value
            claim.user_corrected = True
            flag_modified(claim, "evidence_fragment_ids")
        else:
            claim = ProfileClaim(
                user_id=user_id,
                snapshot_id=snapshot.id,
                group_name=request.group.value,
                claim_key=request.key,
                value_text=request.value,
                evidence_fragment_ids=request.evidence_fragment_ids,
                source=ClaimSource.USER.value,
                user_corrected=True,
            )
            session.add(claim)
        await session.flush()
        return self._claim_to_response(claim)

    async def delete_claim(
        self, session: AsyncSession, user_id: int, claim_id: int
    ) -> None:
        claim = await session.get(ProfileClaim, claim_id)
        if not claim or claim.user_id != user_id or claim.is_deleted:
            raise AppError("PROFILE_CLAIM_NOT_FOUND", "画像结论不存在", 404)
        claim.is_deleted = True
        claim.user_corrected = True
        await session.flush()

    async def diff(
        self, session: AsyncSession, user_id: int, from_period: str, to_period: str
    ) -> ProfileDiffResponse:
        def key_of(claim: ProfileClaim | ProfileClaimResponse) -> tuple[str, str]:
            group = getattr(claim, "group_name", None)
            if group is None:
                group_value = claim.group
                group = group_value.value if hasattr(group_value, "value") else str(group_value)
            key = getattr(claim, "claim_key", None) or claim.key
            return (str(group), key)

        from_snapshot = await self.get_by_period(session, user_id, from_period)
        to_snapshot = await self.get_by_period(session, user_id, to_period)
        from_map = {key_of(item): item for item in from_snapshot.claims}
        to_map = {key_of(item): item for item in to_snapshot.claims}

        added = [item for key, item in to_map.items() if key not in from_map]
        removed = [item for key, item in from_map.items() if key not in to_map]
        changed = []
        for key, item in to_map.items():
            prior = from_map.get(key)
            if prior and prior.value != item.value:
                changed.append({"key": key[1], "from": prior.value, "to": item.value})
        return ProfileDiffResponse(
            from_period=from_period,
            to_period=to_period,
            added=added,
            removed=removed,
            changed=changed,
        )

    async def export_markdown(
        self, session: AsyncSession, user_id: int, period: str
    ) -> str:
        snapshot = await self.get_by_period(session, user_id, period)
        lines = [
            f"# Cairn 成长画像 · {snapshot.period}",
            "",
            f"模型：{snapshot.provider or '-'} / {snapshot.model or '-'}",
            f"提示词版本：{snapshot.prompt_version}",
            f"上一快照：#{snapshot.previous_snapshot_id or '-'}",
            "",
        ]
        groups: dict[str, list] = {}
        for claim in snapshot.claims:
            groups.setdefault(claim.group.value, []).append(claim)
        for group, claims in groups.items():
            lines.extend([f"## {group}", ""])
            for claim in claims:
                evidence = ", ".join(
                    str(value) for value in claim.evidence_fragment_ids
                )
                marker = "用户修正" if claim.user_corrected else claim.source.value
                lines.append(
                    f"- **{claim.key}**：{claim.value}（{marker}；证据 #{evidence}）"
                )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


profile_service = ProfileService()
