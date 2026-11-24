from __future__ import annotations

from pydantic import BaseModel


class DeleteWithProfileRequest(BaseModel):
    """删除记录，并决定这次记录支撑的画像结论是否一起保留。"""

    keep_profile: bool = True


class DeleteWithProfileResponse(BaseModel):
    deleted: bool = True
    profile_claims_removed: int = 0
