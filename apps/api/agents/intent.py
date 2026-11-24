from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from apps.api.agents.state import TaskIntent
from apps.api.agents.tools import AgentToolContext
from apps.api.gateway.schemas import GatewayOptions, GatewayRequest, ResponseFormat

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "intent" / "v1.txt"


class IntentDecision(BaseModel):
    """一次用户输入对应的意图判断结果。"""

    intent: TaskIntent
    reason: str
    use_history: bool = True
    needs_evidence: bool = False


INTENT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent", "reason", "use_history", "needs_evidence"],
    "properties": {
        "intent": {
            "type": "string",
            "enum": [item.value for item in TaskIntent],
        },
        "reason": {"type": "string", "maxLength": 120},
        "use_history": {"type": "boolean"},
        "needs_evidence": {"type": "boolean"},
    },
}

_PROFILE_EDIT_WORDS = ("改画像", "修改画像", "更新我的画像", "补一条", "记住我", "别再", "删掉", "去掉", "不对", "过时")
_PROFILE_REFERENCE = ("画像", "结论", "记成", "记住", "我的")
_META_WORDS = ("你是什么", "你是谁", "你好", "hi", "hello", "在吗", "介绍一下自己")
_TASK_WORDS = (
    "生成", "做成", "做成一份", "整理成", "写一份", "翻译", "导出", "列出来",
    "清单", "时间线", "okr", "计划", "摘要", "总结一下成", "转成",
)
_REVIEW_RULES = [
    (TaskIntent.WEEKLY, ("本周", "这周", "一周", "周报", "weekly")),
    (TaskIntent.PROJECT, ("项目", "迭代", "上线", "发布", "project")),
    (TaskIntent.CONVERSATION, ("对话复盘", "复盘这段", "聊天记录", "会话", "conversation")),
    (TaskIntent.GROWTH, ("成长画像", "生成画像", "更新画像", "画像更新", "growth")),
]


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def fallback_intent(
    message: str,
    file_names: list[str],
    direction: str,
    supplement: str,
    has_history_evidence: bool,
) -> IntentDecision:
    """模型不可用或输出无效时的保守兜底：只看明确诉求，绝不因附件默认复盘。"""
    source = f"{message} {supplement} {' '.join(file_names)}".lower()

    lowered = message.lower()
    if any(word in lowered for word in _META_WORDS):
        return IntentDecision(
            intent=TaskIntent.FREE,
            reason="你是在跟我打招呼或问我是谁",
            use_history=False,
            needs_evidence=False,
        )

    if any(word in source for word in _PROFILE_EDIT_WORDS) and any(
        word in source for word in _PROFILE_REFERENCE
    ):
        return IntentDecision(
            intent=TaskIntent.PROFILE_EDIT,
            reason="你说到了要修改画像里的内容",
            use_history=True,
            needs_evidence=True,
        )

    for intent, words in _REVIEW_RULES:
        if any(word in source for word in words):
            return IntentDecision(
                intent=intent,
                reason="你提到了想做一次复盘或画像",
                use_history=True,
                needs_evidence=True,
            )

    if direction and direction != "free" and (file_names or has_history_evidence):
        try:
            intent = TaskIntent(direction)
        except ValueError:
            intent = TaskIntent.FREE
        if intent != TaskIntent.FREE:
            return IntentDecision(
                intent=intent,
                reason="按你选的方向来",
                use_history=True,
                needs_evidence=True,
            )

    if any(word in source for word in _TASK_WORDS):
        return IntentDecision(
            intent=TaskIntent.TASK,
            reason="你想完成一件具体的事，先看看能用哪些能力帮你做",
            use_history=True,
            needs_evidence=True,
        )

    return IntentDecision(
        intent=TaskIntent.FREE,
        reason="先按普通聊天来回应你",
        use_history=has_history_evidence,
        needs_evidence=has_history_evidence,
    )


async def classify_intent(
    tool_ctx: AgentToolContext,
    *,
    message: str,
    file_names: list[str],
    direction: str,
    supplement: str,
    has_history_evidence: bool,
) -> IntentDecision:
    """用模型判断这一轮想做什么；失败时回退到保守规则，绝不阻塞主任务。"""
    fallback = fallback_intent(
        message, file_names, direction, supplement, has_history_evidence
    )
    payload = {
        "用户这句话": message,
        "附件名称": file_names,
        "用户选的方向": direction,
        "用户补充提示": supplement,
        "有历史证据": has_history_evidence,
    }
    request = GatewayRequest(
        task="intent",
        messages=[
            {"role": "system", "content": _load_prompt()},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        options=GatewayOptions(
            response_format=ResponseFormat.JSON_SCHEMA,
            output_schema=INTENT_JSON_SCHEMA,
            max_tokens=200,
            timeout_seconds=10,
        ),
        user_id=tool_ctx.user_id,
    )
    try:
        response = await tool_ctx.model.gateway.complete(
            request, meter=tool_ctx.model.meter
        )
        raw = response.data
        if raw is None and response.content:
            raw = json.loads(response.content)
        if not isinstance(raw, dict):
            return fallback
        decision = IntentDecision.model_validate(raw)
        if not decision.reason.strip():
            decision.reason = fallback.reason
        return decision
    except Exception:  # noqa: BLE001 - 分类失败不能影响正常对话
        return fallback
