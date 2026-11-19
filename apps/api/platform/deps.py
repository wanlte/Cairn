from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.service import decode_token
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.errors import AppError
from apps.api.platform.service import platform_service

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class PlatformIdentity:
    user_id: int
    scopes: tuple[str, ...]
    actor_type: str
    actor_id: str


async def get_platform_identity(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> PlatformIdentity:
    if creds is None:
        raise AppError("UNAUTHORIZED", "缺少令牌", 401, retryable=False)
    token = creds.credentials
    if token.startswith("ck_"):
        key = await platform_service.resolve_key(session, token)
        return PlatformIdentity(
            user_id=key.user_id,
            scopes=tuple(key.scopes_json or []),
            actor_type="API_KEY",
            actor_id=str(key.id),
        )
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise AppError("INVALID_TOKEN", "需要 access 令牌", 401, retryable=False)
    user = await session.get(User, int(payload["sub"]))
    if not user:
        raise AppError("UNAUTHORIZED", "用户不存在", 401, retryable=False)
    return PlatformIdentity(
        user_id=user.id,
        scopes=("*",),
        actor_type="USER",
        actor_id=str(user.id),
    )


def require_scope(scope: str):
    async def _dependency(
        identity: PlatformIdentity = Depends(get_platform_identity),
    ) -> PlatformIdentity:
        if "*" not in identity.scopes and scope not in identity.scopes:
            raise AppError("FORBIDDEN", "这个密钥没有对应权限", 403, retryable=False)
        return identity

    return _dependency
