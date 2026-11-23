from __future__ import annotations

from sqlalchemy import select

from apps.api.db.models.user import User
from apps.api.gateway.metering import LlmCallLog


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


async def test_metrics_overview_is_zero_safe(client):
    headers = await auth_headers(client, "metrics@example.com")

    response = await client.get("/api/v1/metrics/overview", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 30
    for dimension in ("system", "quality", "cost", "behavior", "value", "security"):
        assert dimension in body
    assert body["headline"]["evidence_hit_rate"] == 0.0
    assert body["system"]["total_requests"] == 0
    assert body["quality"]["profile_stability"] == 1.0


async def test_event_tracking_feeds_behavior_and_value(client):
    headers = await auth_headers(client, "events@example.com")

    for event_type in ("registered", "import_completed", "review_generated", "export_used"):
        created = await client.post(
            "/api/v1/metrics/events",
            json={"event_type": event_type, "payload": {"source": "test"}},
            headers=headers,
        )
        assert created.status_code == 201

    behavior = await client.get("/api/v1/metrics/behavior", headers=headers)
    assert behavior.status_code == 200
    funnel = {step["label"]: step["count"] for step in behavior.json()["funnel"]}
    assert funnel["registered"] == 1
    assert funnel["review_generated"] == 1

    value = await client.get("/api/v1/metrics/value", headers=headers)
    assert value.json()["export_count"] == 1


async def test_llm_calls_drive_cost_and_quality(client, db_session):
    from datetime import UTC, datetime
    from uuid import uuid4

    headers = await auth_headers(client, "llm-metrics@example.com")
    user = (
        await db_session.execute(
            select(User).where(User.email == "llm-metrics@example.com")
        )
    ).scalar_one()

    db_session.add(
        LlmCallLog(
            request_id=str(uuid4()),
            user_id=user.id,
            task_type="review",
            provider="deepseek",
            model="deepseek-chat",
            prompt_tokens=100,
            completion_tokens=50,
            cost_cny=0.0012,
            latency_ms=1200,
            retry_count=0,
            status="ok",
            error_code=None,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    await db_session.flush()

    cost = await client.get("/api/v1/metrics/cost", headers=headers)
    assert cost.status_code == 200
    assert cost.json()["total_calls"] == 1
    assert cost.json()["total_tokens"] == 150
    assert cost.json()["total_cost_cny"] > 0

    system = await client.get("/api/v1/metrics/system", headers=headers)
    assert system.json()["latency_p95_ms"] == 1200
    assert system.json()["success_rate"] == 1.0
