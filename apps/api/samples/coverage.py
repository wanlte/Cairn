from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models.extraction import Fragment
from apps.api.db.models.sample import CounterfactualEntry


def _text_of(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in payload.values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (int, float)):
            parts.append(str(value))
    return " ".join(parts)


async def sample_coverage(
    session: AsyncSession,
    user_id: int,
    fragments: list[Fragment],
) -> dict[str, Any]:
    """给一次分析做样本体检：时间跨度、场景、情绪密度、对象多样性与反事实补录。"""
    counterfactuals = (
        await session.execute(
            select(CounterfactualEntry).where(CounterfactualEntry.user_id == user_id)
        )
    ).scalars().all()
    timestamps = [item.created_at for item in fragments if item.created_at]
    span_days = 0.0
    if len(timestamps) >= 2:
        span_days = max(0.0, (max(timestamps) - min(timestamps)).total_seconds() / 86400)

    domains: set[str] = set()
    sources: set[int] = set()
    emotion_hits = 0
    emotion_words = ("生气", "焦虑", "难过", "开心", "愤怒", "烦躁", "害怕", "失望", "委屈")
    for item in fragments:
        payload = item.payload_json or {}
        if item.conversation_id:
            sources.add(item.conversation_id)
        for key in ("domain", "category", "kind", "topic"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                domains.add(value.strip())
        text = _text_of(payload)
        if any(word in text for word in emotion_words) or any(
            key in payload for key in ("frustration", "emotion", "sentiment", "mood", "state")
        ):
            emotion_hits += 1

    total = max(1, len(fragments))
    span_score = min(25.0, span_days / 30 * 25)
    domain_score = min(25.0, len(domains) / 5 * 25)
    emotion_score = min(20.0, emotion_hits / total * 20)
    source_score = min(20.0, len(sources) / 3 * 20)
    counter_score = min(10.0, len(counterfactuals) / 2 * 10)
    score = round(span_score + domain_score + emotion_score + source_score + counter_score)

    reasons: list[str] = []
    if span_days < 7:
        reasons.append("样本时间跨度不足 7 天")
    if len(domains) < 3:
        reasons.append("场景类型比较单一")
    if emotion_hits < total * 0.2:
        reasons.append("情绪标注密度偏低")
    if len(sources) < 2:
        reasons.append("主要来自单一对话对象")
    if not counterfactuals:
        reasons.append("还没有反事实补录，可能只反映你对 AI 的表达")

    level = "较高" if score >= 70 else "中等" if score >= 40 else "较低"
    return {
        "score": score,
        "level": level,
        "low_confidence": score < 40,
        "span_days": round(span_days, 1),
        "scenarios": len(domains),
        "emotion_density": round(emotion_hits / total, 2),
        "sources": len(sources),
        "counterfactuals": len(counterfactuals),
        "reasons": reasons,
        "summary": (
            f"样本体检 {score} 分（{level}）："
            + ("；".join(reasons[:2]) if reasons else "样本覆盖较均衡")
        ),
    }
