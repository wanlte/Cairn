from __future__ import annotations

from apps.api.gateway.providers import BaseProvider
from apps.api.gateway.schemas import (
    GatewayErrorCode,
    GatewayRequest,
    GatewayResponse,
    ProviderCapabilities,
    ProviderName,
    TokenUsage,
    UnifiedError,
)


def fake_response(
    content: str,
    *,
    provider: ProviderName = ProviderName.DEEPSEEK,
    prompt_tokens: int = 100,
    completion_tokens: int = 20,
) -> GatewayResponse:
    return GatewayResponse(
        content=content,
        provider=provider,
        model=f"{provider.value}-fake",
        usage=TokenUsage(
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        ),
    )


class FakeProvider(BaseProvider):
    def __init__(
        self,
        *,
        name: ProviderName = ProviderName.DEEPSEEK,
        capabilities: ProviderCapabilities | None = None,
        outcomes: list[object] | None = None,
    ) -> None:
        self.name = name
        self._capabilities = capabilities or ProviderCapabilities()
        self.outcomes = list(outcomes or [])
        self.requests: list[GatewayRequest] = []

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities.model_copy(deep=True)

    def normalize_error(self, exc: Exception) -> UnifiedError:
        if isinstance(exc, UnifiedError):
            return exc
        return UnifiedError(
            GatewayErrorCode.SERVER_ERROR, "fake provider error", retryable=True
        )

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        self.requests.append(request.model_copy(deep=True))
        outcome = self.outcomes.pop(0) if self.outcomes else fake_response("{}")
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, GatewayResponse):
            return outcome
        return fake_response(str(outcome), provider=self.name)
