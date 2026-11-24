from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from apps.api.agents.tools import AgentToolContext
from apps.api.db.models.profile import ProfileClaim, ProfileSnapshot
from apps.api.db.models.user import User
from apps.api.gateway.langchain_adapter import GatewayChatModel
from apps.api.profile.schemas import ClaimSource
from apps.api.profile.service import ProfileService
from tests.fakes import FakeProvider, fake_response


async def _login(client, email: str) -> dict:
    await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _make_snapshot(db_session, user_id: int) -> ProfileSnapshot:
    snapshot = ProfileSnapshot(
        user_id=user_id,
        period=f"test-{user_id}",
        status="DONE",
        prompt_version="test-v1",
        created_at=datetime.now(UTC),
    )
    db_session.add(snapshot)
    await db_session.flush()
    return snapshot


@pytest.mark.asyncio
async def test_profile_edit_upsert_and_delete(client, db_session, monkeypatch):
    from apps.api.agents.profile_edit import apply_profile_edits

    await _login(client, "profile-edit@cairn.dev")
    user = (
        await db_session.execute(select(User).where(User.email == "profile-edit@cairn.dev"))
    ).scalar_one()
    snapshot = await _make_snapshot(db_session, user.id)
    old = ProfileClaim(
        user_id=user.id,
        snapshot_id=snapshot.id,
        group_name="identity_background",
        claim_key="职业",
        value_text="老师",
        evidence_fragment_ids=[],
        source=ClaimSource.MODEL.value,
    )
    db_session.add(old)
    await db_session.flush()

    output = {
        "actions": [
            {
                "action": "upsert",
                "group": "identity_background",
                "key": "职业",
                "value": "在做 AI 产品",
                "claim_id": 0,
            },
            {
                "action": "delete",
                "group": "identity_background",
                "key": "过时结论",
                "value": "",
                "claim_id": old.id,
            },
        ],
        "summary": "改了职业并删掉旧结论",
    }
    provider = FakeProvider(outcomes=[fake_response(json.dumps(output, ensure_ascii=False))])

    class Gateway:
        async def complete(self, request, meter=None):
            return await provider.complete(request)

    ctx = AgentToolContext(
        session=db_session,
        user_id=user.id,
        credential={},
        model=GatewayChatModel(gateway=Gateway(), user_id=user.id),
    )
    summary = await apply_profile_edits(
        ctx,
        message="我在做 AI 产品，把老师那条删掉",
        supplement="",
        period="edit-test",
        service=ProfileService(),
    )
    assert "已更新画像" in summary

    claims = (
        await db_session.execute(
            select(ProfileClaim).where(ProfileClaim.user_id == user.id)
        )
    ).scalars().all()
    career = next(item for item in claims if item.claim_key == "职业")
    assert career.value_text == "在做 AI 产品"
    assert career.source == ClaimSource.USER.value
    assert career.user_corrected is True
    assert old.is_deleted is True
    assert old.user_corrected is True


@pytest.mark.asyncio
async def test_profile_edit_creates_snapshot_when_missing(client, db_session):
    from apps.api.agents.profile_edit import apply_profile_edits

    await _login(client, "profile-first@cairn.dev")
    user = (
        await db_session.execute(select(User).where(User.email == "profile-first@cairn.dev"))
    ).scalar_one()
    output = {
        "actions": [
            {
                "action": "upsert",
                "group": "identity_background",
                "key": "身份",
                "value": "独立开发者",
                "claim_id": 0,
            }
        ],
        "summary": "补了一条身份",
    }
    provider = FakeProvider(outcomes=[fake_response(json.dumps(output, ensure_ascii=False))])

    class Gateway:
        async def complete(self, request, meter=None):
            return await provider.complete(request)

    ctx = AgentToolContext(
        session=db_session,
        user_id=user.id,
        credential={},
        model=GatewayChatModel(gateway=Gateway(), user_id=user.id),
    )
    summary = await apply_profile_edits(
        ctx,
        message="记住我是独立开发者",
        supplement="",
        period="first-edit",
        service=ProfileService(),
    )
    assert "已更新画像" in summary
    snapshots = (
        await db_session.execute(
            select(ProfileSnapshot).where(ProfileSnapshot.user_id == user.id)
        )
    ).scalars().all()
    assert len(snapshots) == 1
