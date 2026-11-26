from __future__ import annotations

from pathlib import Path

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "chat" / "v1.txt"
_WITH_EVIDENCE = "【有证据】"
_WITHOUT_EVIDENCE = "【无证据】"


def load_chat_system_prompt(has_evidence: bool) -> str:
    """从版本化提示词文件读取对应场景的系统提示词。"""
    raw = _PROMPT_PATH.read_text(encoding="utf-8")
    if _WITHOUT_EVIDENCE not in raw or _WITH_EVIDENCE not in raw:
        raise RuntimeError("聊天系统提示词缺少场景标记")
    with_evidence, without_evidence = raw.split(_WITHOUT_EVIDENCE, 1)
    with_evidence = with_evidence.replace(_WITH_EVIDENCE, "", 1).strip()
    return with_evidence if has_evidence else without_evidence.strip()
