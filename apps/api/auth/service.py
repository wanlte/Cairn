from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.db.models.user import User
from apps.api.errors import AppError

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)


def _create_token(user_id: int, token_type: str, expires: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "type": token_type, "iat": now, "exp": now + expires}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_access_token(user_id: int) -> str:
    return _create_token(
        user_id, "access", timedelta(minutes=get_settings().jwt_access_ttl_minutes)
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        user_id, "refresh", timedelta(days=get_settings().jwt_refresh_ttl_days)
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise AppError("INVALID_TOKEN", "令牌无效或已过期", 401, retryable=False) from e


async def register_user(session: AsyncSession, email: str, password: str) -> User:
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing:
        raise AppError("EMAIL_EXISTS", "邮箱已注册", 409, retryable=False)
    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    await session.flush()
    return user


async def login_user(session: AsyncSession, email: str, password: str) -> tuple[str, str]:
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "邮箱或密码错误", 401, retryable=False)
    return create_access_token(user.id), create_refresh_token(user.id)


async def refresh_tokens(session: AsyncSession, refresh_token: str) -> tuple[str, str]:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise AppError("INVALID_TOKEN", "需要 refresh 令牌", 401, retryable=False)
    user = await session.get(User, int(payload["sub"]))
    if not user:
        raise AppError("INVALID_TOKEN", "用户不存在", 401, retryable=False)
    return create_access_token(user.id), create_refresh_token(user.id)
