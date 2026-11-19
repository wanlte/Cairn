from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.base import get_session
from apps.api.db.models.platform import AuditLog, PairRelationship
from apps.api.logging import request_id_var
from apps.api.platform.deps import PlatformIdentity, get_platform_identity, require_scope
from apps.api.platform.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyResponse,
    AuditLogResponse,
    ConsentGrant,
    ConsentResponse,
    PairCreate,
    PairResponse,
)
from apps.api.platform.service import platform_service

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])


def _pair_response(item: PairRelationship) -> PairResponse:
    return PairResponse(
        id=item.id,
        user_a_id=item.user_a_id,
        user_b_id=item.user_b_id,
        status=item.status,
        created_by=item.created_by,
        note=item.note,
        confirmed_at=item.confirmed_at,
        revoked_at=item.revoked_at,
        created_at=item.created_at,
    )


def _audit_response(item: AuditLog) -> AuditLogResponse:
    return AuditLogResponse(
        id=item.id,
        user_id=item.user_id,
        actor_type=item.actor_type,
        action=item.action,
        target_type=item.target_type,
        target_id=item.target_id,
        request_id=item.request_id,
        metadata=item.metadata_json or {},
        created_at=item.created_at,
    )


@router.post("/keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    payload: ApiKeyCreate,
    identity: PlatformIdentity = Depends(get_platform_identity),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCreated:
    result = await platform_service.create_key(session, identity.user_id, payload)
    await platform_service.log_audit(
        session,
        action="api_key.created",
        user_id=identity.user_id,
        actor_type=identity.actor_type,
        actor_id=identity.actor_id,
        target_type="api_key",
        target_id=str(result.id),
        request_id=request_id_var.get(),
        metadata={"scopes": result.scopes, "name": result.name},
    )
    await session.commit()
    return result


@router.get("/keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    identity: PlatformIdentity = Depends(get_platform_identity),
    session: AsyncSession = Depends(get_session),
) -> list[ApiKeyResponse]:
    return await platform_service.list_keys(session, identity.user_id)


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: int,
    identity: PlatformIdentity = Depends(get_platform_identity),
    session: AsyncSession = Depends(get_session),
) -> None:
    await platform_service.revoke_key(session, identity.user_id, key_id)
    await platform_service.log_audit(
        session,
        action="api_key.revoked",
        user_id=identity.user_id,
        actor_type=identity.actor_type,
        actor_id=identity.actor_id,
        target_type="api_key",
        target_id=str(key_id),
        request_id=request_id_var.get(),
    )
    await session.commit()


@router.post("/consents", response_model=ConsentResponse, status_code=201)
async def grant_consent(
    payload: ConsentGrant,
    identity: PlatformIdentity = Depends(get_platform_identity),
    session: AsyncSession = Depends(get_session),
) -> ConsentResponse:
    result = await platform_service.grant_consent(session, identity.user_id, payload)
    await platform_service.log_audit(
        session,
        action="consent.granted",
        user_id=identity.user_id,
        actor_type=identity.actor_type,
        actor_id=identity.actor_id,
        target_type="consent",
        target_id=str(result.id),
        request_id=request_id_var.get(),
        metadata={"consent_type": payload.consent_type, "version": payload.version},
    )
    await session.commit()
    return result


@router.get("/consents", response_model=list[ConsentResponse])
async def list_consents(
    consent_type: str | None = Query(default=None),
    identity: PlatformIdentity = Depends(get_platform_identity),
    session: AsyncSession = Depends(get_session),
) -> list[ConsentResponse]:
    return await platform_service.list_consents(session, identity.user_id, consent_type)


@router.delete("/consents/{consent_id}", status_code=204)
async def revoke_consent(
    consent_id: int,
    identity: PlatformIdentity = Depends(get_platform_identity),
    session: AsyncSession = Depends(get_session),
) -> None:
    await platform_service.revoke_consent(session, identity.user_id, consent_id)
    await platform_service.log_audit(
        session,
        action="consent.revoked",
        user_id=identity.user_id,
        actor_type=identity.actor_type,
        actor_id=identity.actor_id,
        target_type="consent",
        target_id=str(consent_id),
        request_id=request_id_var.get(),
    )
    await session.commit()


@router.post("/pairs", response_model=PairResponse, status_code=201)
async def create_pair(
    payload: PairCreate,
    identity: PlatformIdentity = Depends(get_platform_identity),
    session: AsyncSession = Depends(get_session),
) -> PairResponse:
    item = await platform_service.create_pair(
        session, identity.user_id, payload.counterpart_email, payload.note
    )
    await platform_service.log_audit(
        session,
        action="pair.created",
        user_id=identity.user_id,
        actor_type=identity.actor_type,
        actor_id=identity.actor_id,
        target_type="pair",
        target_id=str(item.id),
        request_id=request_id_var.get(),
    )
    await session.commit()
    return _pair_response(item)


@router.get("/pairs", response_model=list[PairResponse])
async def list_pairs(
    identity: PlatformIdentity = Depends(require_scope("pair:read")),
    session: AsyncSession = Depends(get_session),
) -> list[PairResponse]:
    items = await platform_service.list_pairs(session, identity.user_id)
    return [_pair_response(item) for item in items]


@router.post("/pairs/{pair_id}/confirm", response_model=PairResponse)
async def confirm_pair(
    pair_id: int,
    identity: PlatformIdentity = Depends(get_platform_identity),
    session: AsyncSession = Depends(get_session),
) -> PairResponse:
    item = await platform_service.confirm_pair(session, identity.user_id, pair_id)
    await platform_service.log_audit(
        session,
        action="pair.confirmed",
        user_id=identity.user_id,
        actor_type=identity.actor_type,
        actor_id=identity.actor_id,
        target_type="pair",
        target_id=str(pair_id),
        request_id=request_id_var.get(),
    )
    await session.commit()
    return _pair_response(item)


@router.delete("/pairs/{pair_id}", status_code=204)
async def revoke_pair(
    pair_id: int,
    identity: PlatformIdentity = Depends(get_platform_identity),
    session: AsyncSession = Depends(get_session),
) -> None:
    await platform_service.revoke_pair(session, identity.user_id, pair_id)
    await platform_service.log_audit(
        session,
        action="pair.revoked",
        user_id=identity.user_id,
        actor_type=identity.actor_type,
        actor_id=identity.actor_id,
        target_type="pair",
        target_id=str(pair_id),
        request_id=request_id_var.get(),
    )
    await session.commit()


@router.get("/audit", response_model=list[AuditLogResponse])
async def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    identity: PlatformIdentity = Depends(require_scope("audit:read")),
    session: AsyncSession = Depends(get_session),
) -> list[AuditLogResponse]:
    rows = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.user_id == identity.user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [_audit_response(item) for item in rows]
