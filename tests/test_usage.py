from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from apps.api.gateway.metering import LlmCallLog


async def register_and_login(client, email: str) -> tuple[int, dict[str, str]]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    return user_id, {"Authorization": f"Bearer {response.json()['access_token']}"}


async def add_log(db_session, user_id: int, *, task: str = "extract") -> None:
    db_session.add(
        LlmCallLog(
            request_id=str(uuid4()),
            user_id=user_id,
            task_type=task,
            provider="deepseek",
            model="deepseek-chat",
            prompt_tokens=100,
            completion_tokens=50,
            cost_cny=Decimal("0.000300"),
            latency_ms=120,
            retry_count=0,
            status="ok",
        )
    )
    await db_session.flush()


async def test_usage_summary_and_calls_are_scoped_to_current_user(client, db_session):
    user_id, headers = await register_and_login(client, "usage-owner@x.com")
    other_id, _ = await register_and_login(client, "usage-other@x.com")
    await add_log(db_session, user_id)
    await add_log(db_session, user_id, task="review")
    await add_log(db_session, other_id)

    summary = await client.get("/api/v1/usage/summary", headers=headers)
    assert summary.status_code == 200
    items = summary.json()["items"]
    assert len(items) == 2
    assert sum(item["calls"] for item in items) == 2
    assert all(item["provider"] == "deepseek" for item in items)

    calls = await client.get("/api/v1/usage/calls?limit=10", headers=headers)
    assert calls.status_code == 200
    assert len(calls.json()["items"]) == 2
    assert calls.json()["next_cursor"] is None
    assert {item["provider"] for item in calls.json()["items"]} == {"deepseek"}
