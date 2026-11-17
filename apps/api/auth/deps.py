from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.service import decode_token
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.errors import AppError

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if creds is None:
        raise AppError("UNAUTHORIZED", "缺少令牌", 401, retryable=False)
    payload = decode_token(creds.credentials)
    if payload.get("type") != "access":
        raise AppError("INVALID_TOKEN", "需要 access 令牌", 401, retryable=False)
    user = await session.get(User, int(payload["sub"]))
    if not user:
        raise AppError("UNAUTHORIZED", "用户不存在", 401, retryable=False)
    return user
