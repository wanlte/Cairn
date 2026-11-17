from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import ConfigDict, Field

from apps.api.gateway.schemas import GatewayOptions, GatewayRequest


def _to_gateway_messages(messages: Sequence[BaseMessage]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, SystemMessage):
            role = "system"
        elif isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            role = "user"
        result.append({"role": role, "content": str(message.content)})
    return result


class GatewayChatModel(BaseChatModel):
    """把 LangChain 消息翻译成 ModelGateway 请求的自定义模型适配器。

    LangGraph 节点里只用这个适配器；它内部把调用转回 ModelGateway.complete，
    因此能力矩阵、降级链、限流、熔断与计量全部沿用现有治理能力。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    gateway: Any = Field(exclude=True)
    user_id: int
    task: str = "agent"
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    meter: Any = Field(default=None, exclude=True)

    @property
    def _llm_type(self) -> str:
        return "cairn-model-gateway"

    def _options(self) -> GatewayOptions:
        return GatewayOptions(temperature=self.temperature, max_tokens=self.max_tokens)

    def _request(self, messages: Sequence[BaseMessage]) -> GatewayRequest:
        return GatewayRequest(
            task=self.task,
            messages=_to_gateway_messages(messages),
            options=self._options(),
            model=self.model,
            user_id=self.user_id,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError("请使用异步调用：LangGraph 节点在 async 上下文中运行")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        response = await self.gateway.complete(self._request(messages), meter=self.meter)
        generation = ChatGeneration(message=AIMessage(content=response.content))
        return ChatResult(generations=[generation])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        raise NotImplementedError("请使用异步流式调用")

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        response = await self.gateway.complete(self._request(messages), meter=self.meter)
        text = response.content
        step = max(1, len(text) // 20)
        for index in range(0, len(text), step):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=text[index : index + step]))
            if run_manager:
                run_manager.on_llm_new_token(chunk.text)
            yield chunk
