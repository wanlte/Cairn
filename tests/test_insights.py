from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from apps.api.db.models.extraction import ExtractionRun, Fragment
from apps.api.db.models.ingestion import RawConversation, TurnPair
from apps.api.db.models.profile import ProfileClaim, ProfileSnapshot
from apps.api.db.models.sample import CounterfactualEntry
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


async def seed_fragment(db_session, user_id: int, payload: dict) -> None:
    marker = uuid4().hex[:10]
    conversation = RawConversation(
        user_id=user_id,
        source_type="text",
        source_ref=f"seed-{marker}",
        title="种子记录",
        content_hash=f"conv-{marker}",
        raw_text="一段记录",
        time_precision="INFERRED",
    )
    db_session.add(conversation)
    await db_session.flush()
    turn = TurnPair(
        user_id=user_id,
        conversation_id=conversation.id,
        seq=1,
        user_content="一段记录",
        assistant_content="",
        content_hash=f"turn-{marker}",
        time_precision="INFERRED",
        role_confidence=1.0,
    )
    db_session.add(turn)
    await db_session.flush()
    run = ExtractionRun(
        user_id=user_id,
        conversation_id=conversation.id,
        status="DONE",
        total=1,
        processed=1,
        failed=0,
        prompt_version="test-v1",
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add(
        Fragment(
            user_id=user_id,
            run_id=run.id,
            conversation_id=conversation.id,
            turn_pair_id=turn.id,
            kind="knowledge",
            payload_json=payload,
            content_hash=f"frag-{marker}",
        )
    )
    await db_session.flush()


async def test_drift_curve_returns_snapshots_with_claims(client, db_session):
    headers = await auth_headers(client, "drift@example.com")
    user = (
        await db_session.execute(select(User).where(User.email == "drift@example.com"))
    ).scalar_one()

    for period, value in (("2026-10", "以前更看重稳定"), ("2026-11", "现在更看重成长")):
        snapshot = ProfileSnapshot(
            user_id=user.id,
            period=period,
            status="DONE",
            prompt_version="test-v1",
        )
        db_session.add(snapshot)
        await db_session.flush()
        db_session.add(
            ProfileClaim(
                user_id=user.id,
                snapshot_id=snapshot.id,
                group_name="cognitive_style",
                claim_key="取舍",
                value_text=value,
                source="MODEL",
            )
        )
    await db_session.flush()

    response = await client.get("/api/v1/insights/drift", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_snapshots"] == 2
    assert [point["period"] for point in body["points"]] == ["2026-10", "2026-11"]
    assert body["points"][1]["claims"][0]["value"] == "现在更看重成长"

    filtered = await client.get(
        "/api/v1/insights/drift", params={"group": "identity_background"}, headers=headers
    )
    assert filtered.json()["points"][0]["claims"] == []


async def test_relation_graph_is_built_from_records(client, db_session):
    headers = await auth_headers(client, "graph@example.com")
    user = (
        await db_session.execute(select(User).where(User.email == "graph@example.com"))
    ).scalar_one()

    await seed_fragment(
        db_session,
        user.id,
        {"concept": "样本体检", "domain": "产品", "sender": "导师"},
    )
    for label in ("导师", "同事"):
        db_session.add(
            CounterfactualEntry(
                user_id=user.id,
                prompt_type="to_person",
                content="换个说法试试",
                source_label=label,
            )
        )
    await db_session.flush()

    built = await client.post("/api/v1/insights/graph/rebuild", headers=headers)
    assert built.status_code == 200
    assert built.json()["edges"] >= 2

    response = await client.get("/api/v1/insights/graph", headers=headers)
    assert response.status_code == 200
    body = response.json()
    labels = {node["label"] for node in body["nodes"]}
    assert {"导师", "同事", "产品"}.issubset(labels)
    assert any(edge["kind"] == "person_topic" for edge in body["edges"])
