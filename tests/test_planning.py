from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from apps.api.db.models.planning import PlanBlueprint
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


def test_plan_prompt_contains_required_sections():
    path = Path(__file__).resolve().parents[1] / "prompts" / "plan" / "v1.txt"
    content = path.read_text(encoding="utf-8")

    for key in ("feasibility", "premortem", "two_minute", "if_then", "conflicts", "attribution"):
        assert key in content


async def test_current_plan_and_weekly_fill_loop(client, db_session):
    headers = await auth_headers(client, "plan@example.com")
    user = (
        await db_session.execute(select(User).where(User.email == "plan@example.com"))
    ).scalar_one()

    blueprint = PlanBlueprint(
        user_id=user.id,
        goal="把复盘变成每周动作",
        status="DONE",
        payload_json={
            "two_minute": "今天写下第一条",
            "if_then": [{"condition": "想拖延时", "action": "只做两分钟"}],
        },
        coverage_json={},
        prompt_version="plan-v1",
    )
    db_session.add(blueprint)
    await db_session.flush()

    current = await client.get("/api/v1/plans/current", headers=headers)
    assert current.status_code == 200
    assert current.json()["goal"] == "把复盘变成每周动作"

    filled = await client.post(
        f"/api/v1/plans/{blueprint.id}/weekly",
        json={
            "week": "2026-W47",
            "done": "写了第一条",
            "blocked": "",
            "learning": "先做小的更容易开始",
        },
        headers=headers,
    )
    assert filled.status_code == 201
    assert filled.json()["week"] == "2026-W47"

    updated = await client.post(
        f"/api/v1/plans/{blueprint.id}/weekly",
        json={
            "week": "2026-W47",
            "done": "改过了",
            "blocked": "时间不够",
            "learning": "下周再试",
        },
        headers=headers,
    )
    assert updated.json()["done"] == "改过了"

    after = await client.get("/api/v1/plans/current", headers=headers)
    assert len(after.json()["weekly_fills"]) == 1
    assert after.json()["weekly_fills"][0]["blocked"] == "时间不够"

    listing = await client.get("/api/v1/plans", headers=headers)
    assert len(listing.json()) == 1
