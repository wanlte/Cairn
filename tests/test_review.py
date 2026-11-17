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
        {
            "trait": "先确认约束",
            "polarity": "POSITIVE",
            "evidence": "先问排序稳定性",
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


def patch_review_factory(monkeypatch, output: dict) -> None:
    provider = FakeProvider(outcomes=[fake_response(json.dumps(output, ensure_ascii=False))])

    async def fake_factory(*args, **kwargs):
        return ModelGateway([provider]), None, "fake-review-model", ProviderName.DEEPSEEK

    monkeypatch.setattr("apps.api.review.service.build_gateway_for_user", fake_factory)


def patch_extraction_factory(monkeypatch) -> None:
    provider = FakeProvider(
        outcomes=[fake_response(json.dumps(EXTRACTION_OUTPUT, ensure_ascii=False))]
    )

    async def fake_factory(*args, **kwargs):
        return ModelGateway([provider]), None, "fake-model", ProviderName.DEEPSEEK

    monkeypatch.setattr(
        "apps.api.extraction.service.build_gateway_for_user", fake_factory
    )


async def create_fragments(client, headers: dict[str, str], monkeypatch) -> list[int]:
    patch_extraction_factory(monkeypatch)
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


def review_output(fragment_id: int) -> dict:
    return {
        "overview": {
            "dialogue_count": 1,
            "domain_distribution": [{"domain": "backend", "count": 1}],
            "investment_distribution": [{"topic": "pagination", "count": 1}],
            "comparison_with_last_period": "首次复盘",
        },
        "key_events": [
            {
                "fragment_id": fragment_id,
                "background": "分页方案选择",
                "my_judgment": "游标分页更好",
                "actual_outcome": "尚未观察到结果",
            }
        ],
        "judgments": [
            {
                "fragment_id": fragment_id,
                "verdict": "UNVERIFIED",
                "attribution": "VERIFICATION_MISSING",
                "reason": "结果尚未出现",
                "evidence_fragment_ids": [fragment_id],
            }
        ],
        "cognitive_changes": [
            {
                "old_belief": "offset 够用",
                "new_belief": "稳定排序键更可靠",
                "evidence_fragment_ids": [fragment_id],
            }
        ],
        "action_items": [
            {
                "content": "给游标分页补一组稳定性测试",
                "verification": "测试覆盖同 sort key 的翻页不重复不漏项",
                "evidence_fragment_ids": [fragment_id],
            },
            {
                "content": "记录一次真实分页耗时",
                "verification": "报告中有 p95 耗时数字",
                "evidence_fragment_ids": [fragment_id],
            },
        ],
    }


async def test_review_generates_five_sections_and_accepts_feedback(client, monkeypatch):
    headers = await auth_headers(client, "review-a@x.com")
    fragment_ids = await create_fragments(client, headers, monkeypatch)
    patch_review_factory(monkeypatch, review_output(fragment_ids[0]))

    response = await client.post(
        "/api/v1/reviews",
        json={"period": "2026-W47", "provider": "deepseek"},
        headers=headers,
    )

    assert response.status_code == 201
    report = response.json()
    assert report["status"] == "DONE"
    assert report["prompt_version"] == "review-v1"
    assert report["overview"]["dialogue_count"] == 1
    sections = {item["section"] for item in report["items"]}
    assert sections == {"key_event", "judgment", "cognitive_change"}
    assert len(report["action_items"]) == 2
    judgment = next(item for item in report["items"] if item["section"] == "judgment")
    assert judgment["verdict"] == "UNVERIFIED"

    feedback = await client.post(
        f"/api/v1/reviews/items/{judgment['id']}/feedback",
        json={"decision": "AGREE", "note": "确实还没验证"},
        headers=headers,
    )
    assert feedback.status_code == 200
    assert feedback.json()["feedback"]["decision"] == "AGREE"


async def test_review_drops_items_with_invalid_evidence(client, monkeypatch):
    headers = await auth_headers(client, "review-b@x.com")
    await create_fragments(client, headers, monkeypatch)
    patch_review_factory(monkeypatch, review_output(999999))

    response = await client.post(
        "/api/v1/reviews",
        json={"period": "2026-W48", "provider": "deepseek"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["status"] == "DONE"
    assert response.json()["items"] == []


async def test_review_failure_is_persisted(client, monkeypatch):
    headers = await auth_headers(client, "review-c@x.com")
    await create_fragments(client, headers, monkeypatch)
    patch_review_factory(monkeypatch, {})

    response = await client.post(
        "/api/v1/reviews",
        json={"period": "2026-W49", "provider": "deepseek"},
        headers=headers,
    )

    assert response.status_code == 201
    report = response.json()
    assert report["status"] == "FAILED"
    assert report["error_code"]
    assert report["items"] == []
