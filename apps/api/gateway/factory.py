from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.credentials import service as credential_service
from apps.api.errors import AppError
from apps.api.gateway.providers import build_provider
from apps.api.gateway.schemas import ProviderName
from apps.api.gateway.service import ModelGateway


def env_credential(provider: ProviderName) -> tuple[str, str | None, str | None]:
    settings = get_settings()
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


async def build_gateway_for_user(
    session: AsyncSession,
    user_id: int,
    *,
    credential_id: int | None = None,
    provider: ProviderName | None = None,
    model: str | None = None,
) -> tuple[ModelGateway, int | None, str | None, ProviderName | None]:
    if credential_id is not None:
        credentials = await credential_service.list_credentials(session, user_id)
        primary = await credential_service.get_credential(session, user_id, credential_id)
        if not primary.is_active:
            raise AppError("CREDENTIAL_INACTIVE", "凭证已停用", 409, retryable=False)
        ordered = [primary] + [
            item for item in credentials if item.id != primary.id and item.is_active
        ]
        providers = [
            build_provider(
                provider=ProviderName(item.provider),
                api_key=credential_service.decrypt_api_key(item.api_key_encrypted),
                base_url=item.base_url,
                model=model or item.model,
            )
            for item in ordered
        ]
        return (
            ModelGateway(providers),
            primary.id,
            model or primary.model,
            ProviderName(primary.provider),
        )

    if provider is not None:
        api_key, base_url, env_model = env_credential(provider)
        gateway_provider = build_provider(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model or env_model,
        )
        return ModelGateway([gateway_provider]), None, model or env_model, provider

    raise AppError(
        "CREDENTIAL_REQUIRED",
        "请提供 credential_id 或 provider（使用本地环境变量凭证）",
        400,
        retryable=False,
    )
