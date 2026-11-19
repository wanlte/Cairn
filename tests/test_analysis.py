from __future__ import annotations

from sqlalchemy import select

from apps.api.analysis.service import _score_signals, analysis_service
from apps.api.db.models.extraction import ExtractionRun, Fragment
from apps.api.db.models.ingestion import RawConversation, TurnPair
from apps.api.db.models.review import ReviewItem, ReviewReport
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


async def seed_item(client, db_session, email: str, text: str):
    headers = await auth_headers(client, email)
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()

    preview = await client.post(
        "/api/v1/ingestion/preview",
        json={"source_type": "diary", "text": f"## 2026-11-10\n{text}"},
        headers=headers,
    )
    assert preview.status_code == 200
    committed = await client.post(
        "/api/v1/ingestion/commit",
        json={"preview_id": preview.json()["preview_id"], "corrections": []},
        headers=headers,
    )
    assert committed.status_code == 200

    conversation = (
        await db_session.execute(
            select(RawConversation).where(RawConversation.user_id == user.id)
        )
    ).scalar_one()
    turn = (
        await db_session.execute(
            select(TurnPair).where(TurnPair.conversation_id == conversation.id)
        )
    ).scalar_one()

    run = ExtractionRun(
        user_id=user.id,
        conversation_id=conversation.id,
        status="DONE",
        total=1,
        processed=1,
        failed=0,
        prompt_version="test-v1",
    )
    db_session.add(run)
    await db_session.flush()
    fragment = Fragment(
        user_id=user.id,
        run_id=run.id,
        conversation_id=conversation.id,
        turn_pair_id=turn.id,
        kind="state",
        payload_json={"frustration": text},
        content_hash=f"analysis-{user.id}-{conversation.id}",
    )
    db_session.add(fragment)
    await db_session.flush()

    report = ReviewReport(
        user_id=user.id,
        period="2026-11",
        status="DONE",
        overview_json={},
        prompt_version="test-v1",
    )
    db_session.add(report)
    await db_session.flush()
    item = ReviewItem(
        user_id=user.id,
        report_id=report.id,
        section="judgment",
        fragment_id=fragment.id,
        verdict="UNVERIFIED",
        attribution="NONE",
        evidence_fragment_ids=[fragment.id],
        payload_json={"reason": "先记下来，还没看到结果"},
        confidence_low=0.3,
        confidence_high=0.7,
        reasoning_chain_json=["先看到记录", "再对照证据", "暂时不下结论"],
        conflict_with_json=[],
        appeal_status="NONE",
    )
    db_session.add(item)
    await db_session.flush()
    return headers, user.id, fragment, item


def test_score_signals_detects_social_desirability():
    score, signals = _score_signals("其实我更想做研究，但大家都觉得应该先赚钱")

    assert score > 0.5
    assert "其实我更想" in signals
    assert "大家都觉得" in signals


async def test_desirability_is_detected_and_exposed(client, db_session):
    headers, user_id, fragment, _item = await seed_item(
        client,
        db_session,
        "desire@example.com",
        "其实我更想做研究，但大家都觉得应该先赚钱",
    )

    flags = await analysis_service.detect_desirability(db_session, user_id, [fragment])
    assert len(flags) == 1
    assert flags[0].score > 0

    response = await client.get("/api/v1/analysis/desirability", headers=headers)
    assert response.status_code == 200
    assert any(row["fragment_id"] == fragment.id for row in response.json())


async def test_appeal_goes_through_review_loop(client, db_session):
    headers, _user_id, _fragment, item = await seed_item(
        client, db_session, "appeal@example.com", "这段先放着，之后再看"
    )

    created = await client.post(
        "/api/v1/analysis/appeals",
        params={"item_id": item.id},
        json={"reason": "我当时其实不是这个意思"},
        headers=headers,
    )
    assert created.status_code == 201
    appeal = created.json()
    assert appeal["status"] == "PENDING"

    listed = await client.get("/api/v1/analysis/appeals", headers=headers)
    assert len(listed.json()) == 1

    resolved = await client.post(
        f"/api/v1/analysis/appeals/{appeal['id']}/resolve",
        json={"decision": "ACCEPTED", "note": "已按你的说明修订"},
        headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "ACCEPTED"

    report = await client.get(f"/api/v1/reviews/{item.report_id}", headers=headers)
    judgment = next(row for row in report.json()["items"] if row["id"] == item.id)
    assert judgment["appeal_status"] == "ACCEPTED"


async def test_evidence_chain_exposes_reasoning_and_fragments(client, db_session):
    headers, _user_id, fragment, item = await seed_item(
        client, db_session, "chain@example.com", "这段先放着，之后再看"
    )

    response = await client.get(
        f"/api/v1/analysis/evidence-chain/{item.id}", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reasoning_chain"] == ["先看到记录", "再对照证据", "暂时不下结论"]
    assert body["confidence_low"] == 0.3
    assert body["confidence_high"] == 0.7
    assert any(row["fragment_id"] == fragment.id for row in body["evidence"])
