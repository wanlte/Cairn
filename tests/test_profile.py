from __future__ import annotations

import json

from apps.api.gateway.schemas import ProviderName
from apps.api.gateway.service import ModelGateway
from tests.fakes import FakeProvider, fake_response

EXTRACTION_OUTPUT = {
    "events": [
        {
            "what": "采用游标分页",
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


async def auth_headers(client, email: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def patch_factory(monkeypatch, module: str, output: dict) -> None:
    provider = FakeProvider(outcomes=[fake_response(json.dumps(output, ensure_ascii=False))])

    async def fake_factory(*args, **kwargs):
        return ModelGateway([provider]), None, "fake-model", ProviderName.DEEPSEEK

    monkeypatch.setattr(f"{module}.build_gateway_for_user", fake_factory)


async def create_fragments(client, headers, monkeypatch) -> list[int]:
    patch_factory(monkeypatch, "apps.api.extraction.service", EXTRACTION_OUTPUT)
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


def profile_output(fragment_id: int, *, verification_value: str = "先看文档再动手") -> dict:
    return {
        "identity_background": [
            {
                "key": "技术栈倾向",
                "value": "偏后端与架构",
                "evidence_fragment_ids": [fragment_id],
            }
        ],
        "cognitive_style": [
            {
                "key": "验证习惯",
                "value": verification_value,
                "evidence_fragment_ids": [fragment_id],
            }
        ],
        "attention_trajectory": [
            {"domain": "backend", "count": 2, "evidence_fragment_ids": [fragment_id]}
        ],
        "high_frequency_pitfalls": [
            {"pitfall": "未验证结果", "count": 1, "evidence_fragment_ids": [fragment_id]}
        ],
        "growth_signals": [
            {
                "signal": "新掌握概念数",
                "value": "1",
                "evidence_fragment_ids": [fragment_id],
            }
        ],
    }


async def test_profile_generation_groups_and_evidence(client, monkeypatch):
    headers = await auth_headers(client, "profile-a@x.com")
    fragment_ids = await create_fragments(client, headers, monkeypatch)
    patch_factory(
        monkeypatch, "apps.api.profile.service", profile_output(fragment_ids[0])
    )

    response = await client.post(
        "/api/v1/profile/generate",
        json={"period": "2026-W47", "provider": "deepseek"},
        headers=headers,
    )

    assert response.status_code == 201
    snapshot = response.json()
    assert snapshot["status"] == "DONE"
    assert snapshot["prompt_version"] == "profile-v1"
    groups = {item["group"] for item in snapshot["claims"]}
    assert groups == {
        "identity_background",
        "cognitive_style",
        "attention_trajectory",
        "high_frequency_pitfalls",
        "growth_signals",
    }
    assert all(item["evidence_fragment_ids"] for item in snapshot["claims"])


async def test_user_correction_is_inherited_and_not_regenerated(client, monkeypatch):
    headers = await auth_headers(client, "profile-b@x.com")
    fragment_ids = await create_fragments(client, headers, monkeypatch)
    patch_factory(
        monkeypatch, "apps.api.profile.service", profile_output(fragment_ids[0])
    )
    await client.post(
        "/api/v1/profile/generate",
        json={"period": "2026-W47", "provider": "deepseek"},
        headers=headers,
    )
    corrected = await client.put(
        "/api/v1/profile/claims",
        json={
            "group": "cognitive_style",
            "key": "验证习惯",
            "value": "先写测试再实现",
            "evidence_fragment_ids": [],
        },
        headers=headers,
    )
    assert corrected.status_code == 200
    assert corrected.json()["user_corrected"] is True

    patch_factory(
        monkeypatch,
        "apps.api.profile.service",
        profile_output(fragment_ids[0], verification_value="先看论文再实现"),
    )
    second = await client.post(
        "/api/v1/profile/generate",
        json={"period": "2026-W48", "provider": "deepseek"},
        headers=headers,
    )
    second_claims = second.json()["claims"]
    verification = [
        item for item in second_claims if item["key"] == "验证习惯"
    ]
    assert len(verification) == 1
    assert verification[0]["value"] == "先写测试再实现"
    assert verification[0]["source"] == "USER"

    diff = await client.get(
        "/api/v1/profile/diff?from_period=2026-W47&to_period=2026-W48",
        headers=headers,
    )
    assert diff.status_code == 200
    assert diff.json()["from_period"] == "2026-W47"


async def test_deleted_claim_is_not_regenerated(client, monkeypatch):
    headers = await auth_headers(client, "profile-c@x.com")
    fragment_ids = await create_fragments(client, headers, monkeypatch)
    patch_factory(
        monkeypatch, "apps.api.profile.service", profile_output(fragment_ids[0])
    )
    first = await client.post(
        "/api/v1/profile/generate",
        json={"period": "2026-W47", "provider": "deepseek"},
        headers=headers,
    )
    claim = next(
        item for item in first.json()["claims"] if item["key"] == "技术栈倾向"
    )
    deleted = await client.delete(
        f"/api/v1/profile/claims/{claim['id']}", headers=headers
    )
    assert deleted.status_code == 204

    patch_factory(
        monkeypatch, "apps.api.profile.service", profile_output(fragment_ids[0])
    )
    second = await client.post(
        "/api/v1/profile/generate",
        json={"period": "2026-W48", "provider": "deepseek"},
        headers=headers,
    )
    assert all(item["key"] != "技术栈倾向" for item in second.json()["claims"])


async def test_profile_failure_is_persisted(client, monkeypatch):
    headers = await auth_headers(client, "profile-d@x.com")
    await create_fragments(client, headers, monkeypatch)
    patch_factory(monkeypatch, "apps.api.profile.service", {})

    response = await client.post(
        "/api/v1/profile/generate",
        json={"period": "2026-W47", "provider": "deepseek"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["status"] == "FAILED"
    assert response.json()["error_code"]
