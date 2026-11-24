from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models.extraction import Fragment
from apps.api.db.models.profile import ProfileClaim


async def fragment_ids_for_conversations(
    session: AsyncSession, user_id: int, conversation_ids: list[int]
) -> set[int]:
    """找出这些对话下的全部碎片编号。"""
    if not conversation_ids:
        return set()
    rows = (
        await session.execute(
            select(Fragment.id).where(
                Fragment.user_id == user_id,
                Fragment.conversation_id.in_(conversation_ids),
            )
        )
    ).scalars().all()
    return {int(value) for value in rows}


async def drop_profile_for_fragments(
    session: AsyncSession, user_id: int, fragment_ids: set[int]
) -> int:
    """删除记录时不保留画像：废弃证据只来自这些碎片的结论。

    返回被废弃的结论数。复用 ProfileClaim.is_deleted，让生成的 rejected
    机制知道这些结论不要再出现；证据还有其它来源的结论保持不动。
    """
    if not fragment_ids:
        return 0
    claims = (
        await session.execute(
            select(ProfileClaim).where(
                ProfileClaim.user_id == user_id,
                ProfileClaim.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    changed = 0
    for claim in claims:
        evidence = {int(value) for value in (claim.evidence_fragment_ids or [])}
        if evidence and evidence.issubset(fragment_ids):
            claim.is_deleted = True
            claim.user_corrected = True
            changed += 1
    await session.flush()
    return changed
