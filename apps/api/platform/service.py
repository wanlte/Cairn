from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models.platform import ApiKey, AuditLog, ConsentRecord, PairRelationship
from apps.api.db.models.user import User
from apps.api.errors import AppError
from apps.api.platform.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyResponse,
    ConsentGrant,
    ConsentResponse,
)

ALLOWED_SCOPES = {
    "profile:read",
    "review:read",
    "plan:read",
    "simulate:write",
    "pair:read",
    "audit:read",
}


def hash_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        lowered = key.lower()
        if any(part in lowered for part in ("key", "token", "secret", "password")):
            result[key] = "[REDACTED]"
        else:
            result[key] = value
    return result


def _key_response(item: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=item.id,
        name=item.name,
        key_prefix=item.key_prefix,
        scopes=list(item.scopes_json or []),
        created_at=item.created_at,
        expires_at=item.expires_at,
        last_used_at=item.last_used_at,
        revoked_at=item.revoked_at,
    )


def _consent_response(item: ConsentRecord) -> ConsentResponse:
    return ConsentResponse(
        id=item.id,
        consent_type=item.consent_type,
        version=item.version,
        counterpart_id=item.counterpart_id,
        granted=item.granted and item.revoked_at is None,
        granted_at=item.granted_at,
        revoked_at=item.revoked_at,
    )


class PlatformService:
    async def create_key(
        self, session: AsyncSession, user_id: int, payload: ApiKeyCreate
    ) -> ApiKeyCreated:
        unknown = [scope for scope in payload.scopes if scope not in ALLOWED_SCOPES]
        if unknown:
            raise AppError("INVALID_SCOPE", f"不支持的权限：{', '.join(unknown)}", 400, retryable=False)
        token = f"ck_{secrets.token_urlsafe(32)}"
        item = ApiKey(
            user_id=user_id,
            name=payload.name,
            key_prefix=token[:16],
            key_hash=hash_key(token),
            scopes_json=list(payload.scopes),
            expires_at=(
                datetime.now(UTC) + timedelta(days=payload.expires_in_days)
                if payload.expires_in_days
                else None
            ),
        )
        session.add(item)
        await session.flush()
        response = _key_response(item)
        return response.model_copy(update={"token": token})

    async def list_keys(self, session: AsyncSession, user_id: int) -> list[ApiKeyResponse]:
        rows = (
            await session.execute(
                select(ApiKey)
                .where(ApiKey.user_id == user_id)
                .order_by(ApiKey.created_at.desc())
            )
        ).scalars().all()
        return [_key_response(item) for item in rows]

    async def revoke_key(self, session: AsyncSession, user_id: int, key_id: int) -> None:
        item = await session.get(ApiKey, key_id)
        if not item or item.user_id != user_id:
            raise AppError("API_KEY_NOT_FOUND", "找不到这个密钥", 404, retryable=False)
        item.revoked_at = datetime.now(UTC)

    async def resolve_key(self, session: AsyncSession, token: str) -> ApiKey:
        item = (
            await session.execute(
                select(ApiKey).where(ApiKey.key_hash == hash_key(token))
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if not item or item.revoked_at or (item.expires_at and item.expires_at < now):
            raise AppError("INVALID_API_KEY", "这个密钥无效或已过期", 401, retryable=False)
        item.last_used_at = now
        return item

    async def grant_consent(
        self, session: AsyncSession, user_id: int, payload: ConsentGrant
    ) -> ConsentResponse:
        item = ConsentRecord(
            user_id=user_id,
            consent_type=payload.consent_type,
            version=payload.version,
            counterpart_id=payload.counterpart_id,
            granted=True,
            payload_json=_sanitize_metadata(payload.payload),
            granted_at=datetime.now(UTC),
        )
        session.add(item)
        await session.flush()
        return _consent_response(item)

    async def list_consents(
        self,
        session: AsyncSession,
        user_id: int,
        consent_type: str | None = None,
    ) -> list[ConsentResponse]:
        stmt = select(ConsentRecord).where(ConsentRecord.user_id == user_id)
        if consent_type:
            stmt = stmt.where(ConsentRecord.consent_type == consent_type)
        rows = (await session.execute(stmt.order_by(ConsentRecord.granted_at.desc()))).scalars().all()
        return [_consent_response(item) for item in rows]

    async def revoke_consent(
        self, session: AsyncSession, user_id: int, consent_id: int
    ) -> None:
        item = await session.get(ConsentRecord, consent_id)
        if not item or item.user_id != user_id:
            raise AppError("CONSENT_NOT_FOUND", "找不到这条授权", 404, retryable=False)
        item.revoked_at = datetime.now(UTC)

    async def has_consent(
        self,
        session: AsyncSession,
        user_id: int,
        consent_type: str,
        counterpart_id: int | None = None,
    ) -> bool:
        stmt = select(ConsentRecord).where(
            ConsentRecord.user_id == user_id,
            ConsentRecord.consent_type == consent_type,
            ConsentRecord.revoked_at.is_(None),
        )
        if counterpart_id is not None:
            stmt = stmt.where(ConsentRecord.counterpart_id == counterpart_id)
        else:
            stmt = stmt.where(ConsentRecord.counterpart_id.is_(None))
        return (await session.execute(stmt.limit(1))).scalar_one_or_none() is not None

    async def create_pair(
        self, session: AsyncSession, user_id: int, counterpart_email: str, note: str | None
    ) -> PairRelationship:
        counterpart = (
            await session.execute(select(User).where(User.email == counterpart_email))
        ).scalar_one_or_none()
        if not counterpart:
            raise AppError("PAIR_USER_NOT_FOUND", "没有找到这位用户", 404, retryable=False)
        if counterpart.id == user_id:
            raise AppError("PAIR_SELF", "不能和自己建立关系", 400, retryable=False)
        first, second = sorted((user_id, counterpart.id))
        existing = (
            await session.execute(
                select(PairRelationship).where(
                    PairRelationship.user_a_id == first,
                    PairRelationship.user_b_id == second,
                    PairRelationship.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        item = PairRelationship(
            user_a_id=first,
            user_b_id=second,
            status="PENDING",
            created_by=user_id,
            note=note,
        )
        session.add(item)
        await session.flush()
        return item

    async def confirm_pair(
        self, session: AsyncSession, user_id: int, pair_id: int
    ) -> PairRelationship:
        item = await session.get(PairRelationship, pair_id)
        if not item or user_id not in (item.user_a_id, item.user_b_id):
            raise AppError("PAIR_NOT_FOUND", "找不到这段关系", 404, retryable=False)
        if item.created_by == user_id:
            raise AppError("PAIR_SELF_CONFIRM", "需要对方确认", 400, retryable=False)
        item.status = "ACTIVE"
        item.confirmed_at = datetime.now(UTC)
        return item

    async def revoke_pair(self, session: AsyncSession, user_id: int, pair_id: int) -> None:
        item = await session.get(PairRelationship, pair_id)
        if not item or user_id not in (item.user_a_id, item.user_b_id):
            raise AppError("PAIR_NOT_FOUND", "找不到这段关系", 404, retryable=False)
        item.status = "REVOKED"
        item.revoked_at = datetime.now(UTC)

    async def list_pairs(
        self, session: AsyncSession, user_id: int
    ) -> list[PairRelationship]:
        rows = (
            await session.execute(
                select(PairRelationship)
                .where(
                    (PairRelationship.user_a_id == user_id)
                    | (PairRelationship.user_b_id == user_id)
                )
                .order_by(PairRelationship.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def log_audit(
        self,
        session: AsyncSession,
        action: str,
        user_id: int | None = None,
        actor_type: str = "USER",
        actor_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        session.add(
            AuditLog(
                user_id=user_id,
                actor_type=actor_type,
                actor_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                request_id=request_id,
                metadata_json=_sanitize_metadata(metadata),
            )
        )


platform_service = PlatformService()
