from __future__ import annotations

import json

from apps.api.evaluation.service import load_dataset
from apps.api.gateway.schemas import ProviderName
from apps.api.gateway.service import ModelGateway
from tests.fakes import FakeProvider, fake_response

EXTRACTION_OUTPUT = {
    "events": [
        {
            "what": "决定采用游标分页",
            "domain": "backend",
            "decision": "稳定排序键替代 offset",
            "outcome_status": "UNVERIFIED",
            "confidence": 0.8,
        }
    ],
    "knowledge": [
        {
            "concept": "游标分页",
            "summary": "稳定排序键替代 offset",
            "category": "concept",
            "mastery_hint": "used",
        }
    ],
    "traits": [
        {"trait": "先确认约束", "polarity": "POSITIVE", "evidence": "先问排序稳定性"}
    ],
    "state": {"frustration": "LOW", "curiosity": "HIGH", "clarity": "HIGH"},
}


class EmbeddingFakeProvider(FakeProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * 1536
            vector[0] = 1.0 if "游标" in text or "分页" in text else 0.0
            vectors.append(vector)
        return vectors


async def auth_headers(client, email: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def patch_gateway(monkeypatch, module: str, output: dict, *, embed: bool = False) -> None:
    provider_cls = EmbeddingFakeProvider if embed else FakeProvider
    provider = provider_cls(outcomes=[fake_response(json.dumps(output, ensure_ascii=False))])

    async def fake_factory(*args, **kwargs):
        return ModelGateway([provider]), None, "fake-model", ProviderName.DEEPSEEK

    monkeypatch.setattr(f"{module}.build_gateway_for_user", fake_factory)


async def create_fragments(client, headers, monkeypatch) -> list[int]:
    patch_gateway(monkeypatch, "apps.api.extraction.service", EXTRACTION_OUTPUT)
    preview = await client.post(
        "/api/v1/ingestion/preview",
        json={"source_type": "markdown", "text": "## 用户\nq\n## 助手\na"},
        headers=headers,
    )
    conversation_id = (
        await client.post(
            "/api/v1/ingestion/commit",
            json={"preview_id": preview.json()["preview_id"]},
            headers=headers,
        )
    ).json()["conversation_id"]
    await client.post(
        "/api/v1/extraction/runs",
        json={"conversation_id": conversation_id, "provider": "deepseek"},
        headers=headers,
    )
    fragments = await client.get("/api/v1/extraction/fragments", headers=headers)
    return [item["id"] for item in fragments.json()]


async def test_dataset_inventory(client):
    response = await client.get("/api/v1/evaluation/datasets")
    assert response.status_code == 200
    datasets = {item["name"]: item for item in response.json()}
    assert datasets["extraction_50.jsonl"]["rows"] == 50
    assert datasets["retrieval_30.jsonl"]["rows"] == 30
    assert datasets["review_30.jsonl"]["rows"] == 30
    assert all(item["synthetic"] for item in datasets.values())


async def test_extraction_evaluation_uses_labels(client, monkeypatch):
    headers = await auth_headers(client, "eval-extract@x.com")
    label = load_dataset("extraction_50.jsonl", 1)[0]
    patch_gateway(monkeypatch, "apps.api.evaluation.service", label["expected"])

    response = await client.post(
        "/api/v1/evaluation/extraction",
        json={"provider": "deepseek", "limit": 1},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sample_count"] == 1
    assert body["accuracy"] == 1.0
    assert body["passed"] is True


async def test_review_evaluation_compares_latest_report(client, monkeypatch):
    headers = await auth_headers(client, "eval-review@x.com")
    fragment_ids = await create_fragments(client, headers, monkeypatch)
    review_output = {
        "overview": {
            "dialogue_count": 1,
            "domain_distribution": [],
            "investment_distribution": [],
            "comparison_with_last_period": "",
        },
        "key_events": [],
        "judgments": [
            {
                "fragment_id": fragment_ids[0],
                "verdict": "UNVERIFIED",
                "attribution": "VERIFICATION_MISSING",
                "reason": "结果未出现",
                "evidence_fragment_ids": [fragment_ids[0]],
            }
        ],
        "cognitive_changes": [],
        "action_items": [],
    }
    patch_gateway(monkeypatch, "apps.api.review.service", review_output)
    await client.post(
        "/api/v1/reviews",
        json={"period": "2026-W47", "provider": "deepseek"},
        headers=headers,
    )

    response = await client.post(
        "/api/v1/evaluation/review",
        json={"limit": 1},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["matched"] == 1
    assert body["consistency"] == 1.0
    assert body["passed"] is True


async def test_retrieval_evaluation_computes_recall(client, monkeypatch):
    headers = await auth_headers(client, "eval-retrieval@x.com")
    await create_fragments(client, headers, monkeypatch)

    provider = EmbeddingFakeProvider()
    async def fake_provider_for(*args, **kwargs):
        return ModelGateway([provider]), provider

    monkeypatch.setattr(
        "apps.api.retrieval.service._provider_for", fake_provider_for
    )
    await client.post(
        "/api/v1/retrieval/index", json={"provider": "deepseek"}, headers=headers
    )

    response = await client.post(
        "/api/v1/evaluation/retrieval",
        json={"provider": "deepseek", "limit": 1},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["hit_at_5"] == 1
    assert body["recall_at_5"] == 1.0
    assert body["passed"] is True
