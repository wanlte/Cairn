from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.deps import get_current_user
from apps.api.config import Settings, get_settings
from apps.api.credentials import service as credential_service
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.errors import AppError
from apps.api.gateway.metering import session_meter
from apps.api.gateway.providers import build_provider
from apps.api.gateway.ratelimit import get_shared_limiter
from apps.api.gateway.schemas import (
    GatewayOptions,
    GatewayRequest,
    GatewayResponse,
    ProviderName,
    UnifiedError,
)
from apps.api.gateway.service import ModelGateway

router = APIRouter(prefix="/api/v1/gateway", tags=["gateway"])


class GatewayCallRequest(BaseModel):
    credential_id: int | None = None
    provider: ProviderName | None = None
    task: str = Field(min_length=1, max_length=64)
    messages: list[dict]
    options: GatewayOptions = Field(default_factory=GatewayOptions)
    model: str | None = None


def _env_credential(provider: ProviderName, settings: Settings) -> tuple[str, str | None, str | None]:
    fields = {
        ProviderName.DEEPSEEK: (
            settings.deepseek_api_key,
            settings.deepseek_base_url,
            settings.deepseek_model,
        ),
        ProviderName.VOLCENGINE: (
            settings.volcengine_api_key,
            settings.volcengine_base_url,
            settings.volcengine_model,
        ),
        ProviderName.HUNYUAN: (
            settings.hunyuan_api_key,
            settings.hunyuan_base_url,
            settings.hunyuan_model,
        ),
        ProviderName.OPENAI_COMPAT: (
            settings.openai_compat_api_key,
            settings.openai_compat_base_url,
            settings.openai_compat_model,
        ),
    }
    api_key, base_url, model = fields[provider]
    if not api_key:
        raise AppError(
            "ENV_CREDENTIAL_MISSING",
            f"本地环境变量未配置 {provider.value.upper()}_API_KEY",
            400,
            retryable=False,
        )
    return api_key, base_url, model


@router.post("/complete", response_model=GatewayResponse)
async def complete(
    payload: GatewayCallRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> GatewayResponse:
    settings = get_settings()
    options = payload.options.model_copy(deep=True)
    if idempotency_key and not options.idempotency_key:
        options.idempotency_key = idempotency_key
    if options.timeout_seconds is None:
        options.timeout_seconds = (
            settings.gateway_read_timeout_review
            if payload.task in {"review", "profile", "chat"}
            else settings.gateway_read_timeout_extract
        )

    providers = []
    credential_id: int | None = None
    resolved_model = payload.model

    if payload.credential_id is not None:
        credentials = await credential_service.list_credentials(session, current_user.id)
        primary = await credential_service.get_credential(
            session, current_user.id, payload.credential_id
        )
        if not primary.is_active:
            raise AppError("CREDENTIAL_INACTIVE", "凭证已停用", 409, retryable=False)
        ordered = [primary] + [
            item for item in credentials if item.id != primary.id and item.is_active
        ]
        for credential in ordered:
            providers.append(
                build_provider(
                    provider=ProviderName(credential.provider),
                    api_key=credential_service.decrypt_api_key(
                        credential.api_key_encrypted
                    ),
                    base_url=credential.base_url,
                    model=payload.model or credential.model,
                )
            )
        credential_id = primary.id
        resolved_model = payload.model or primary.model
    elif payload.provider is not None:
        api_key, base_url, model = _env_credential(payload.provider, settings)
        providers.append(
            build_provider(
                provider=payload.provider,
                api_key=api_key,
                base_url=base_url,
                model=payload.model or model,
            )
        )
        resolved_model = payload.model or model
    else:
        raise AppError(
            "CREDENTIAL_REQUIRED",
            "请提供 credential_id 或 provider（使用本地环境变量凭证）",
            400,
            retryable=False,
        )

    gateway = ModelGateway(providers, limiter=get_shared_limiter())

    meter = session_meter(session)

    request = GatewayRequest(
        task=payload.task,
        messages=payload.messages,
        options=options,
        model=resolved_model,
        user_id=current_user.id,
        credential_id=credential_id,
    )

    try:
        response = await gateway.complete(request, meter=meter)
    except UnifiedError as exc:
        await session.commit()
        raise AppError(
            exc.code.value,
            exc.message,
            exc.status_code,
            exc.retryable,
        ) from exc

    await session.commit()
    return response
