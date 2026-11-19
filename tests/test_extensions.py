from __future__ import annotations

from sqlalchemy import select

from apps.api.db.models.planning import PlanBlueprint
from apps.api.db.models.platform import PairRelationship
from apps.api.db.models.user import User


async def auth_headers(client, email: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_daily_question_is_stable_and_answerable(client):
    headers = await auth_headers(client, "daily@example.com")

    first = await client.get("/api/v1/extensions/daily", headers=headers)
    assert first.status_code == 200
    question = first.json()
    assert question["question"]

    again = await client.get("/api/v1/extensions/daily", headers=headers)
    assert again.json()["id"] == question["id"]

    answered = await client.post(
        f"/api/v1/extensions/daily/{question['id']}/answer",
        json={"answer": "我最想先跟导师说，因为他会追问证据。"},
        headers=headers,
    )
    assert answered.status_code == 200
    assert "导师" in answered.json()["answer"]


async def test_export_supports_json_markdown_and_html(client, db_session):
    headers = await auth_headers(client, "export@example.com")
    user = (
        await db_session.execute(select(User).where(User.email == "export@example.com"))
    ).scalar_one()
    db_session.add(
        PlanBlueprint(
            user_id=user.id,
            goal="把复盘变成每周动作",
            status="DONE",
            payload_json={"two_minute": "今天写下第一条"},
            coverage_json={},
            prompt_version="plan-v1",
        )
    )
    await db_session.flush()

    for fmt, expected in (
        ("json", '"goal"'),
        ("md", "# 行动规划"),
        ("html", "<!doctype html>"),
    ):
        response = await client.get(
            "/api/v1/exports/plan", params={"format": fmt}, headers=headers
        )
        assert response.status_code == 200
        assert expected in response.json()["content"]

    invalid = await client.get(
        "/api/v1/exports/plan", params={"format": "pdf"}, headers=headers
    )
    assert invalid.status_code == 422


async def test_open_api_rejects_key_without_scope(client):
    headers = await auth_headers(client, "openapi@example.com")
    created = await client.post(
        "/api/v1/platform/keys",
        json={"name": "reader", "scopes": ["review:read"]},
        headers=headers,
    )
    assert created.status_code == 201

    key_headers = {"Authorization": f"Bearer {created.json()['token']}"}
    denied = await client.get("/api/v1/open/profile", headers=key_headers)
    assert denied.status_code == 403

    allowed = await client.get("/api/v1/open/reviews", headers=key_headers)
    assert allowed.status_code == 200


async def test_pair_analysis_requires_confirmed_relationship(client, db_session):
    headers = await auth_headers(client, "pair@example.com")
    user = (
        await db_session.execute(select(User).where(User.email == "pair@example.com"))
    ).scalar_one()
    other = User(email="partner@example.com", password_hash="not-used")
    db_session.add(other)
    await db_session.flush()
    pair = PairRelationship(
        user_a_id=user.id,
        user_b_id=other.id,
        status="PENDING",
        created_by=user.id,
    )
    db_session.add(pair)
    await db_session.flush()

    response = await client.post(
        "/api/v1/extensions/pair-analysis",
        json={"pair_id": pair.id},
        headers=headers,
    )
    assert response.status_code == 403
