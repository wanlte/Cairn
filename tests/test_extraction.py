from __future__ import annotations

import json

from apps.api.gateway.schemas import ProviderName
from apps.api.gateway.service import ModelGateway
from tests.fakes import FakeProvider, fake_response

VALID_OUTPUT = {
    "events": [
        {
            "what": "决定改用游标分页",
            "domain": "backend",
            "decision": "采用稳定排序键",
            "outcome_status": "UNVERIFIED",
            "confidence": 0.8,
        }
    ],
    "knowledge": [
        {
            "concept": "游标分页",
            "summary": "用稳定排序键替代 offset",
            "category": "concept",
            "mastery_hint": "used",
        }
    ],
    "traits": [
        {
            "trait": "先确认约束再实现",
            "polarity": "POSITIVE",
            "evidence": "先问清楚排序稳定性",
        }
    ],
    "state": {"frustration": "LOW", "curiosity": "HIGH", "clarity": "HIGH"},
}


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


async def create_conversation(client, headers: dict[str, str], text: str) -> int:
    preview = await client.post(
        "/api/v1/ingestion/preview",
        json={"source_type": "markdown", "text": text},
        headers=headers,
    )
    assert preview.status_code == 200
    committed = await client.post(
        "/api/v1/ingestion/commit",
        json={"preview_id": preview.json()["preview_id"]},
        headers=headers,
    )
    assert committed.status_code == 200
    return committed.json()["conversation_id"]


def patch_factory(monkeypatch, provider: FakeProvider) -> None:
    async def fake_factory(*args, **kwargs):
        return ModelGateway([provider]), None, "fake-model", ProviderName.DEEPSEEK

    monkeypatch.setattr(
        "apps.api.extraction.service.build_gateway_for_user", fake_factory
    )


async def test_extraction_run_produces_four_fragment_kinds(client, monkeypatch):
    headers = await auth_headers(client, "extract-a@x.com")
    conversation_id = await create_conversation(
        client,
        headers,
        "# Extract Demo\n## 用户\n如何做分页？\n## 助手\n用游标分页。",
    )
    patch_factory(
        monkeypatch,
        FakeProvider(outcomes=[fake_response(json.dumps(VALID_OUTPUT, ensure_ascii=False))]),
    )

    response = await client.post(
        "/api/v1/extraction/runs",
        json={"conversation_id": conversation_id, "provider": "deepseek"},
        headers=headers,
    )

    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "DONE"
    assert run["total"] == 1
    assert run["processed"] == 1
    assert run["failed"] == 0
    assert run["prompt_version"] == "extraction-v1"

    fragments = await client.get(
        f"/api/v1/extraction/fragments?run_id={run['id']}", headers=headers
    )
    assert fragments.status_code == 200
    kinds = {item["kind"] for item in fragments.json()}
    assert kinds == {"event", "knowledge", "trait", "state"}
    assert all(item["payload"]["source_turn_id"] for item in fragments.json())


async def test_extraction_idempotency_key_returns_same_run(client, monkeypatch):
    headers = await auth_headers(client, "extract-b@x.com")
    conversation_id = await create_conversation(
        client, headers, "## 用户\nq\n## 助手\na"
    )
    provider = FakeProvider(
        outcomes=[fake_response(json.dumps(VALID_OUTPUT, ensure_ascii=False))]
    )
    patch_factory(monkeypatch, provider)

    payload = {
        "conversation_id": conversation_id,
        "provider": "deepseek",
        "idempotency_key": "extract-conv-idem-001",
    }
    first = await client.post(
        "/api/v1/extraction/runs", json=payload, headers=headers
    )
    second = await client.post(
        "/api/v1/extraction/runs", json=payload, headers=headers
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(provider.requests) == 1


async def test_invalid_output_marks_run_failed_without_silent_drop(client, monkeypatch):
    headers = await auth_headers(client, "extract-c@x.com")
    conversation_id = await create_conversation(
        client, headers, "## 用户\nq\n## 助手\na"
    )
    patch_factory(monkeypatch, FakeProvider(outcomes=[fake_response("{}")]))

    response = await client.post(
        "/api/v1/extraction/runs",
        json={"conversation_id": conversation_id, "provider": "deepseek"},
        headers=headers,
    )

    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "FAILED"
    assert run["failed"] == 1
    assert run["error_json"]
    fragments = await client.get("/api/v1/extraction/fragments", headers=headers)
    assert fragments.json() == []


async def test_knowledge_fragments_merge_and_increment_occurred_count(client, monkeypatch):
    headers = await auth_headers(client, "extract-d@x.com")
    conversation_id = await create_conversation(
        client,
        headers,
        "## 用户\nq1\n## 助手\na1\n## 用户\nq2\n## 助手\na2",
    )
    patch_factory(
        monkeypatch,
        FakeProvider(
            outcomes=[
                fake_response(json.dumps(VALID_OUTPUT, ensure_ascii=False)),
                fake_response(json.dumps(VALID_OUTPUT, ensure_ascii=False)),
            ]
        ),
    )

    await client.post(
        "/api/v1/extraction/runs",
        json={"conversation_id": conversation_id, "provider": "deepseek"},
        headers=headers,
    )
    fragments = await client.get(
        "/api/v1/extraction/fragments?kind=knowledge", headers=headers
    )

    assert len(fragments.json()) == 1
    assert fragments.json()[0]["payload"]["occurred_count"] == 2
