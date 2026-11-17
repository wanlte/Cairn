from __future__ import annotations

import json

from apps.api.gateway.schemas import ProviderName
from apps.api.gateway.service import ModelGateway
from tests.fakes import FakeProvider, fake_response

EXTRACTION_OUTPUT = {
    "events": [
        {
            "what": "决定采用游标分页",
            "domain": "backend",
            "decision": "使用稳定排序键",
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

PROFILE_OUTPUT = {
    "identity_background": [
        {
            "key": "技术栈倾向",
            "value": "偏后端",
            "evidence_fragment_ids": [],
        }
    ],
    "cognitive_style": [],
    "attention_trajectory": [],
    "high_frequency_pitfalls": [],
    "growth_signals": [],
}


class EmbeddingFakeProvider(FakeProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * 1536
            if "游标" in text or "分页" in text:
                vector[0] = 1.0
            elif "后端" in text:
                vector[1] = 1.0
            else:
                vector[2] = 1.0
            vectors.append(vector)
        return vectors


def patch_retrieval(monkeypatch, provider: EmbeddingFakeProvider) -> None:
    async def fake_provider_for(*args, **kwargs):
        return ModelGateway([provider]), provider

    monkeypatch.setattr("apps.api.retrieval.service._provider_for", fake_provider_for)


def patch_extraction(monkeypatch) -> None:
    provider = FakeProvider(
        outcomes=[fake_response(json.dumps(EXTRACTION_OUTPUT, ensure_ascii=False))]
    )

    async def fake_factory(*args, **kwargs):
        return ModelGateway([provider]), None, "fake-model", ProviderName.DEEPSEEK

    monkeypatch.setattr(
        "apps.api.extraction.service.build_gateway_for_user", fake_factory
    )


async def auth_headers(client, email: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_fragments(client, headers, monkeypatch) -> list[int]:
    patch_extraction(monkeypatch)
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


async def test_index_and_hybrid_search(client, monkeypatch):
    headers = await auth_headers(client, "rag-a@x.com")
    await create_fragments(client, headers, monkeypatch)
    patch_retrieval(monkeypatch, EmbeddingFakeProvider())

    indexed = await client.post(
        "/api/v1/retrieval/index", json={"provider": "deepseek"}, headers=headers
    )
    assert indexed.status_code == 200
    assert indexed.json()["indexed"] >= 1

    searched = await client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "游标分页怎么做",
            "provider": "deepseek",
            "top_k": 5,
        },
        headers=headers,
    )

    assert searched.status_code == 200
    body = searched.json()
    assert body["used_vector"] is True
    assert body["used_bm25"] is True
    assert body["items"]
    assert body["items"][0]["fragment_id"]


async def test_search_filters_domain_and_platform(client, monkeypatch):
    headers = await auth_headers(client, "rag-b@x.com")
    await create_fragments(client, headers, monkeypatch)
    patch_retrieval(monkeypatch, EmbeddingFakeProvider())
    await client.post(
        "/api/v1/retrieval/index", json={"provider": "deepseek"}, headers=headers
    )

    matched = await client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "游标分页",
            "provider": "deepseek",
            "filters": {"domain": "backend", "platform": "markdown"},
        },
        headers=headers,
    )
    unmatched = await client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "游标分页",
            "provider": "deepseek",
            "filters": {"domain": "frontend"},
        },
        headers=headers,
    )

    assert len(matched.json()["items"]) >= 1
    assert unmatched.json()["items"] == []


async def test_rerank_uses_gateway_scores(client, monkeypatch):
    headers = await auth_headers(client, "rag-c@x.com")
    fragment_ids = await create_fragments(client, headers, monkeypatch)
    provider = EmbeddingFakeProvider()
    patch_retrieval(monkeypatch, provider)
    await client.post(
        "/api/v1/retrieval/index", json={"provider": "deepseek"}, headers=headers
    )
    provider.outcomes.append(
        fake_response(
            json.dumps(
                {
                    "scores": [
                        {"fragment_id": fragment_ids[0], "score": 0.91},
                    ]
                }
            )
        )
    )

    response = await client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "游标分页",
            "provider": "deepseek",
            "rerank": True,
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["reranked"] is True
    assert response.json()["items"][0]["rerank_score"] == 0.91


async def test_ask_uses_profile_summary(client, monkeypatch):
    headers = await auth_headers(client, "rag-d@x.com")
    fragment_ids = await create_fragments(client, headers, monkeypatch)

    async def fake_profile_factory(*args, **kwargs):
        output = json.loads(json.dumps(PROFILE_OUTPUT))
        for claim in output["identity_background"]:
            claim["evidence_fragment_ids"] = [fragment_ids[0]]
        return (
            ModelGateway([FakeProvider(outcomes=[fake_response(json.dumps(output, ensure_ascii=False))])]),
            None,
            "fake-model",
            ProviderName.DEEPSEEK,
        )

    monkeypatch.setattr(
        "apps.api.profile.service.build_gateway_for_user", fake_profile_factory
    )
    await client.post(
        "/api/v1/profile/generate",
        json={"period": "2026-W47", "provider": "deepseek"},
        headers=headers,
    )

    provider = EmbeddingFakeProvider(outcomes=[fake_response("根据片段，游标分页更稳定。")])
    patch_retrieval(monkeypatch, provider)
    await client.post(
        "/api/v1/retrieval/index", json={"provider": "deepseek"}, headers=headers
    )

    response = await client.post(
        "/api/v1/retrieval/ask",
        json={"query": "我更倾向什么方案？", "provider": "deepseek"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile_used"] is True
    assert "游标分页" in body["answer"]
    assert body["sources"]
