from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr

from apps.api.gateway.schemas import ProviderName


class CredentialSelection(BaseModel):
    """单次请求的凭证选择。所有需要模型的请求 schema 都继承它。

    临时密钥用 SecretStr 承载：不与数据库交互、不参与序列化、不进入日志。
    优先级由 build_gateway_for_user 固定为：临时密钥 > 已保存凭证 > 本机配置。
    """

    credential_id: int | None = None
    provider: ProviderName | None = None
    model: str | None = None
    temporary_api_key: SecretStr | None = Field(
        default=None,
        repr=False,
        exclude=True,
        json_schema_extra={"writeOnly": True, "description": "仅本次使用，不会被保存"},
    )
    temporary_base_url: str | None = Field(default=None, exclude=True)

    def gateway_kwargs(self) -> dict:
        return {
            "credential_id": self.credential_id,
            "provider": self.provider,
            "model": self.model,
            "temporary_api_key": self.temporary_api_key,
            "temporary_base_url": self.temporary_base_url,
        }
