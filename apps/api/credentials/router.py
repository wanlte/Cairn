from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.config import get_settings
from apps.api.credentials import service as credential_service
from apps.api.credentials.schemas import (
    CapabilityView,
    CredentialCreate,
    CredentialResponse,
)
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.errors import AppError
from apps.api.gateway.capabilities import (
    DEFAULT_PROBE_CACHE,
    KNOWN_CAPABILITIES,
    ProbeCache,
    probe_capabilities,
)
from apps.api.gateway.providers import build_provider
from apps.api.gateway.schemas import ProviderName

router = APIRouter(prefix="/api/v1/credentials", tags=["credentials"])


def _require_confirmation(request: Request) -> None:
    settings = get_settings()
    value = request.headers.get(settings.credential_confirm_header, "").lower()
    if value != "confirm":
        raise AppError(
            "CONFIRMATION_REQUIRED",
            f"请通过 {settings.credential_confirm_header}: confirm 二次确认",
            428,
            retryable=False,
        )


def _cache_key(provider: ProviderName, base_url: str | None, model: str | None) -> str:
    return ProbeCache.key(
        provider,
        base_url or "default",
        model or "default",
    )


def _enum_value(value) -> str:
    return getattr(value, "value", str(value))


def _capability_view(provider: ProviderName, capabilities) -> CapabilityView:
    return CapabilityView(
        provider=provider,
        json_schema=capabilities.json_schema,
        structured_output=_enum_value(capabilities.structured_output),
        tools=_enum_value(capabilities.tools),
        thinking=_enum_value(capabilities.thinking),
        context_window=capabilities.context_window,
        max_output_tokens=capabilities.max_output_tokens,
        qps=capabilities.qps,
        concurrency=capabilities.concurrency,
        probed=capabilities.probed,
    )


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[CredentialResponse]:
    credentials = await credential_service.list_credentials(session, current_user.id)
    return [credential_service.credential_to_response(item) for item in credentials]


@router.post("", response_model=CredentialResponse, status_code=201)
async def create_credential(
    payload: CredentialCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CredentialResponse:
    _require_confirmation(request)
    credential = await credential_service.create_credential(
        session, current_user.id, payload
    )
    await session.commit()
    return credential_service.credential_to_response(credential)


@router.get("/capabilities")
async def get_capabilities(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    cache = DEFAULT_PROBE_CACHE
    known = [
        _capability_view(provider, capabilities).model_dump()
        for provider, capabilities in KNOWN_CAPABILITIES.items()
    ]
    credentials = await credential_service.list_credentials(session, current_user.id)
    probed = []
    for credential in credentials:
        provider = ProviderName(credential.provider)
        capabilities = cache.get(
            _cache_key(provider, credential.base_url, credential.model)
        )
        if capabilities is None:
            capabilities = credential.capabilities_json
        if capabilities:
            if isinstance(capabilities, dict):
                probed.append({"credential_id": credential.id, **capabilities})
            else:
                probed.append(
                    {
                        "credential_id": credential.id,
                        **_capability_view(provider, capabilities).model_dump(),
                    }
                )
    return {"known": known, "probed": probed}


@router.post("/{credential_id}/test")
async def test_credential(
    credential_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    credential = await credential_service.get_credential(
        session, current_user.id, credential_id
    )
    provider = build_provider(
        provider=ProviderName(credential.provider),
        api_key=credential_service.decrypt_api_key(credential.api_key_encrypted),
        base_url=credential.base_url,
        model=credential.model,
    )
    capabilities = await probe_capabilities(provider)
    cache_key = _cache_key(provider.name, credential.base_url, credential.model)
    DEFAULT_PROBE_CACHE.set(cache_key, capabilities)
    await credential_service.set_capabilities(
        session, credential, capabilities.model_dump(mode="json")
    )
    await session.commit()
    return {
        "credential_id": credential.id,
        "capabilities": capabilities.model_dump(mode="json"),
    }


@router.delete("/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    _require_confirmation(request)
    await credential_service.delete_credential(session, current_user.id, credential_id)
    await session.commit()
