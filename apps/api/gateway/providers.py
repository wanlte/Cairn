from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from apps.api.config import get_settings
from apps.api.gateway.capabilities import KNOWN_CAPABILITIES
from apps.api.gateway.schemas import (
    GatewayErrorCode,
    GatewayRequest,
    GatewayResponse,
    ProviderCapabilities,
    ProviderName,
    ResponseFormat,
    StreamChunk,
    ThinkingMode,
    TokenUsage,
    ToolSupport,
    UnifiedError,
    redact_snippet,
)


class BaseProvider(ABC):
    name: ProviderName

    @abstractmethod
    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    @abstractmethod
    def normalize_error(self, exc: Exception) -> UnifiedError:
        raise NotImplementedError

    async def complete_stream(
        self, request: GatewayRequest
    ) -> AsyncIterator[StreamChunk]:
        raise UnifiedError(
            GatewayErrorCode.SERVER_ERROR,
            f"{self.name.value} 不支持流式输出",
            retryable=False,
        )
        yield StreamChunk()  # 使其成为 async generator，异常在迭代时抛出

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise UnifiedError(
            GatewayErrorCode.SERVER_ERROR,
            f"{self.name.value} 不支持 embedding",
            retryable=False,
        )


class OpenAICompatProvider(BaseProvider):
    name = ProviderName.OPENAI_COMPAT

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        name: ProviderName = ProviderName.OPENAI_COMPAT,
        capabilities: ProviderCapabilities | None = None,
        client: object | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.name = name
        self._capabilities = capabilities or KNOWN_CAPABILITIES[self.name].model_copy(
            deep=True
        )
        settings = get_settings()
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout or settings.gateway_read_timeout_extract,
            max_retries=0,
        )

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities.model_copy(deep=True)

    def normalize_error(self, exc: Exception) -> UnifiedError:
        if isinstance(exc, UnifiedError):
            return exc
        if isinstance(exc, (APITimeoutError, APIConnectionError, TimeoutError)):
            return UnifiedError(
                GatewayErrorCode.SERVER_ERROR,
                "模型服务超时或连接失败",
                retryable=True,
            )
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            message = str(exc)
            if status == 402:
                return UnifiedError(
                    GatewayErrorCode.QUOTA_EXHAUSTED, "模型供应商余额不足", retryable=False
                )
            if status in {401, 403}:
                return UnifiedError(
                    GatewayErrorCode.AUTH_FAILED, "模型凭证无效", retryable=False
                )
            if status == 404:
                return UnifiedError(
                    GatewayErrorCode.MODEL_NOT_FOUND, "模型不存在或已下线", retryable=False
                )
            if status == 429:
                return UnifiedError(
                    GatewayErrorCode.RATE_LIMIT, "模型供应商限流", retryable=True
                )
            if status is not None and status >= 500:
                return UnifiedError(
                    GatewayErrorCode.SERVER_ERROR, "模型供应商服务错误", retryable=True
                )
            lowered = message.lower()
            if "context" in lowered or "token limit" in lowered:
                return UnifiedError(
                    GatewayErrorCode.CONTEXT_TOO_LONG, "上下文长度超限", retryable=False
                )
            if "balance" in lowered or "quota" in lowered or "insufficient" in lowered:
                return UnifiedError(
                    GatewayErrorCode.QUOTA_EXHAUSTED, "模型供应商余额不足", retryable=False
                )
        return UnifiedError(
            GatewayErrorCode.SERVER_ERROR, "模型调用失败", retryable=False
        )

    def _build_kwargs(self, request: GatewayRequest) -> dict:
        options = request.options
        messages = [dict(message) for message in request.messages]
        capabilities = self.capabilities()

        kwargs: dict = {
            "model": request.model or self.model,
            "messages": messages,
            "temperature": options.temperature,
        }
        if options.max_tokens is not None:
            kwargs["max_tokens"] = options.max_tokens
        if options.timeout_seconds is not None:
            kwargs["timeout"] = options.timeout_seconds

        extra_body = dict(options.extra_body)
        if capabilities.thinking == ThinkingMode.THINKING_PARAM and not extra_body.get(
            "thinking"
        ):
            extra_body["thinking"] = {"type": "enabled"}
        elif capabilities.thinking == ThinkingMode.REASONING_EFFORT and not extra_body.get(
            "reasoning_effort"
        ):
            extra_body["reasoning_effort"] = "high"
        if extra_body:
            kwargs["extra_body"] = extra_body

        if options.tools and capabilities.tools == ToolSupport.SUPPORTED:
            kwargs["tools"] = options.tools

        if options.response_format == ResponseFormat.JSON_SCHEMA:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "cairn_output",
                    "schema": options.output_schema or {"type": "object"},
                    "strict": True,
                },
            }
        elif options.response_format == ResponseFormat.JSON_OBJECT:
            kwargs["response_format"] = {"type": "json_object"}
            if options.output_schema:
                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": (
                            "只输出一个 JSON 对象，并严格符合以下 JSON Schema："
                            f"{options.output_schema}。不要输出解释文字。"
                        ),
                    },
                )
        return kwargs

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        started = time.perf_counter()
        kwargs = self._build_kwargs(request)
        response = await self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        if isinstance(content, list):
            content = "".join(
                str(getattr(part, "text", part)) for part in content
            )
        usage = response.usage
        return GatewayResponse(
            content=content,
            provider=self.name,
            model=request.model or self.model,
            credential_id=request.credential_id,
            usage=TokenUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            ),
            latency_ms=int((time.perf_counter() - started) * 1000),
            raw_response_snippet=redact_snippet(content),
        )

    async def complete_stream(self, request: GatewayRequest) -> AsyncIterator[StreamChunk]:
        """逐 chunk 产出增量文本，最后一个 chunk 携带 usage。

        仅产出正文增量；reasoning/thinking 增量（混元等推理模型）不进入正文。
        个别 OpenAI 兼容端点不支持 stream_options，遇到 400 时去掉该参数重试
        （此时拿不到 usage，计量记 0）。
        """
        kwargs = self._build_kwargs(request)
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}
        try:
            stream = await self._create_stream(kwargs)
            async for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if choices:
                    delta = getattr(choices[0], "delta", None)
                    content = getattr(delta, "content", None) if delta is not None else None
                    if content:
                        if isinstance(content, list):
                            content = "".join(
                                str(getattr(part, "text", part)) for part in content
                            )
                        yield StreamChunk(delta=content)
                usage = getattr(chunk, "usage", None)
                if usage is not None and not choices:
                    yield StreamChunk(
                        usage=TokenUsage(
                            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                        )
                    )
        except Exception as exc:
            raise self.normalize_error(exc) from exc

    async def _create_stream(self, kwargs: dict):
        try:
            return await self._client.chat.completions.create(**kwargs)
        except APIStatusError as exc:
            message = str(exc).lower()
            if getattr(exc, "status_code", None) == 400 and "stream_option" in message:
                kwargs.pop("stream_options", None)
                return await self._client.chat.completions.create(**kwargs)
            raise

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        settings = get_settings()
        models = {
            ProviderName.DEEPSEEK: settings.deepseek_embedding_model,
            ProviderName.VOLCENGINE: settings.volcengine_embedding_model,
            ProviderName.HUNYUAN: settings.hunyuan_embedding_model,
            ProviderName.OPENAI_COMPAT: settings.openai_compat_embedding_model,
        }
        try:
            response = await self._client.embeddings.create(
                model=models[self.name],
                input=texts,
            )
        except Exception as exc:
            raise self.normalize_error(exc) from exc
        return [[float(value) for value in item.embedding] for item in response.data]


class DeepSeekProvider(OpenAICompatProvider):
    name = ProviderName.DEEPSEEK

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        client: object | None = None,
    ) -> None:
        settings = get_settings()
        super().__init__(
            api_key=api_key,
            base_url=base_url or settings.deepseek_base_url,
            model=model or settings.deepseek_model,
            name=self.name,
            client=client,
        )


class VolcengineProvider(OpenAICompatProvider):
    name = ProviderName.VOLCENGINE

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        client: object | None = None,
    ) -> None:
        settings = get_settings()
        super().__init__(
            api_key=api_key,
            base_url=base_url or settings.volcengine_base_url,
            model=model or settings.volcengine_model,
            name=self.name,
            client=client,
        )


class HunyuanProvider(OpenAICompatProvider):
    name = ProviderName.HUNYUAN

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        client: object | None = None,
    ) -> None:
        settings = get_settings()
        super().__init__(
            api_key=api_key,
            base_url=base_url or settings.hunyuan_base_url,
            model=model or settings.hunyuan_model,
            name=self.name,
            client=client,
        )


def build_provider(
    *,
    provider: ProviderName,
    api_key: str,
    base_url: str | None,
    model: str | None,
    client: object | None = None,
    capabilities: ProviderCapabilities | None = None,
) -> BaseProvider:
    settings = get_settings()
    defaults = {
        ProviderName.DEEPSEEK: (settings.deepseek_base_url, settings.deepseek_model),
        ProviderName.VOLCENGINE: (
            settings.volcengine_base_url,
            settings.volcengine_model,
        ),
        ProviderName.HUNYUAN: (settings.hunyuan_base_url, settings.hunyuan_model),
        ProviderName.OPENAI_COMPAT: (None, None),
    }
    resolved_base_url, resolved_model = defaults[provider]
    if not resolved_base_url and not base_url:
        raise UnifiedError(
            GatewayErrorCode.MODEL_NOT_FOUND,
            "OpenAI 兼容端点必须提供 base_url",
            retryable=False,
        )
    return OpenAICompatProvider(
        api_key=api_key,
        base_url=base_url or resolved_base_url,
        model=model or resolved_model or "default",
        name=provider,
        capabilities=capabilities,
        client=client,
    )
