from __future__ import annotations

from sqlalchemy import select

from apps.api.db.models.profile import ProfileClaim, ProfileSnapshot
from apps.api.db.models.review import ReviewItem, ReviewReport
from apps.api.db.models.workspace import WorkspaceTask


async def auth_headers(client, email: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _make_claim(db_session, user_id: int, period: str, fragment_ids: list[int]):
    snapshot = ProfileSnapshot(
        user_id=user_id, period=period, status="DONE", prompt_version="profile-v1"
    )
    db_session.add(snapshot)
    await db_session.flush()
    claim = ProfileClaim(
        user_id=user_id,
        snapshot_id=snapshot.id,
        group_name="关注方向",
        claim_key="focus",
        value_text="专注产品与选题",
        evidence_fragment_ids=fragment_ids,
        source="generated",
    )
    db_session.add(claim)
    await db_session.flush()
    return claim


async def test_delete_review_keep_profile(client, db_session):
    from apps.api.db.models.user import User

    headers = await auth_headers(client, "del-keep@example.com")
    user = (
        await db_session.execute(
            select(User).where(User.email == "del-keep@example.com")
        )
    ).scalar_one()

    report = ReviewReport(
        user_id=user.id, period="2026-11-k", status="DONE",
        overview_json={}, prompt_version="review-v1",
    )
    db_session.add(report)
    await db_session.flush()
    db_session.add(
        ReviewItem(report_id=report.id, user_id=user.id, section="key_event",
                   payload_json={}, evidence_fragment_ids=[101, 102])
    )
    claim = await _make_claim(db_session, user.id, "p-k", [101, 102])
    await db_session.commit()

    result = await client.delete(
        f"/api/v1/reviews/{report.id}?keep_profile=true", headers=headers
    )
    assert result.status_code == 200
    assert result.json()["profile_claims_removed"] == 0

    listing = await client.get("/api/v1/reviews", headers=headers)
    assert all(item["id"] != report.id for item in listing.json())
    refreshed = await db_session.get(ProfileClaim, claim.id)
    assert refreshed.is_deleted is False


async def test_delete_review_without_keep_profile(client, db_session):
    from apps.api.db.models.user import User

    headers = await auth_headers(client, "del-drop@example.com")
    user = (
        await db_session.execute(
            select(User).where(User.email == "del-drop@example.com")
        )
    ).scalar_one()

    report = ReviewReport(
        user_id=user.id, period="2026-11-d", status="DONE",
        overview_json={}, prompt_version="review-v1",
    )
    db_session.add(report)
    await db_session.flush()
    db_session.add(
        ReviewItem(report_id=report.id, user_id=user.id, section="key_event",
                   payload_json={}, evidence_fragment_ids=[201, 202])
    )
    claim = await _make_claim(db_session, user.id, "p-d", [201, 202])
    other = await _make_claim(db_session, user.id, "p-d2", [203])
    await db_session.commit()

    result = await client.delete(
        f"/api/v1/reviews/{report.id}?keep_profile=false", headers=headers
    )
    assert result.status_code == 200
    assert result.json()["profile_claims_removed"] == 1

    refreshed = await db_session.get(ProfileClaim, claim.id)
    assert refreshed.is_deleted is True
    assert refreshed.user_corrected is True
    kept = await db_session.get(ProfileClaim, other.id)
    assert kept.is_deleted is False


async def test_delete_task_without_keep_profile(client, db_session):
    from apps.api.db.models.user import User

    headers = await auth_headers(client, "del-task@example.com")
    user = (
        await db_session.execute(
            select(User).where(User.email == "del-task@example.com")
        )
    ).scalar_one()

    task = WorkspaceTask(
        task_key="task-to-delete", user_id=user.id, status="DONE",
        intent="free", user_message="要删掉的对话",
        conversation_ids_json=[55],
    )
    db_session.add(task)
    await _make_claim(db_session, user.id, "p-task", [301])
    await db_session.commit()

    result = await client.delete(
        "/api/v1/workspace/tasks/task-to-delete?keep_profile=false", headers=headers
    )
    assert result.status_code == 200

    listing = await client.get("/api/v1/workspace/tasks", headers=headers)
    assert all(item["task_id"] != "task-to-delete" for item in listing.json())
    assert result.json()["profile_claims_removed"] == 0
