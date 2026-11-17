from __future__ import annotations

import base64
import hashlib
from collections.abc import Sequence

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.credentials.schemas import CredentialCreate, CredentialResponse
from apps.api.db.models.credential import ModelCredential
from apps.api.errors import AppError
from apps.api.gateway.schemas import ProviderName


def _fernet() -> Fernet:
    settings = get_settings()
    digest = hashlib.sha256(settings.cairn_secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key(api_key: str) -> str:
    return _fernet().encrypt(api_key.encode("utf-8")).decode("ascii")


def decrypt_api_key(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode("ascii")).decode("utf-8")


def mask_api_key(api_key: str) -> str:
    if api_key.startswith("sk-") and len(api_key) > 7:
        return f"sk-****{api_key[-4:]}"
    if len(api_key) <= 4:
        return "****"
    return f"****{api_key[-4:]}"


def credential_to_response(credential: ModelCredential) -> CredentialResponse:
    return CredentialResponse(
        id=credential.id,
        name=credential.name,
        provider=ProviderName(credential.provider),
        base_url=credential.base_url,
        model=credential.model,
        api_key_masked=mask_api_key(decrypt_api_key(credential.api_key_encrypted)),
        is_active=credential.is_active,
        capabilities=credential.capabilities_json,
        created_at=credential.created_at,
    )


async def list_credentials(
    session: AsyncSession, user_id: int
) -> Sequence[ModelCredential]:
    result = await session.execute(
        select(ModelCredential)
        .where(ModelCredential.user_id == user_id)
        .order_by(ModelCredential.id)
    )
    return result.scalars().all()


async def get_credential(
    session: AsyncSession, user_id: int, credential_id: int
) -> ModelCredential:
    credential = await session.get(ModelCredential, credential_id)
    if credential is None or credential.user_id != user_id:
        raise AppError("CREDENTIAL_NOT_FOUND", "凭证不存在", 404, retryable=False)
    return credential


async def create_credential(
    session: AsyncSession, user_id: int, payload: CredentialCreate
) -> ModelCredential:
    credential = ModelCredential(
        user_id=user_id,
        name=payload.name,
        provider=payload.provider.value,
        api_key_encrypted=encrypt_api_key(payload.api_key),
        base_url=payload.base_url,
        model=payload.model,
        is_active=True,
    )
    session.add(credential)
    await session.flush()
    return credential


async def delete_credential(
    session: AsyncSession, user_id: int, credential_id: int
) -> None:
    credential = await get_credential(session, user_id, credential_id)
    await session.delete(credential)
    await session.flush()


async def set_capabilities(
    session: AsyncSession,
    credential: ModelCredential,
    capabilities: dict,
) -> None:
    credential.capabilities_json = capabilities
    await session.flush()
