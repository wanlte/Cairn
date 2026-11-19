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
            "decision": "稳定排序键",
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
        {"trait": "先确认约束", "polarity": "POSITIVE", "evidence": "先问稳定性"}
    ],
    "state": {"frustration": "LOW", "curiosity": "HIGH", "clarity": "HIGH"},
}

REVIEW_OUTPUT = {
    "overview": {
        "dialogue_count": 1,
        "domain_distribution": [],
        "investment_distribution": [],
        "comparison_with_last_period": "首次复盘",
    },
    "key_events": [],
    "judgments": [],
    "cognitive_changes": [],
    "action_items": [
        {
            "content": "补一组稳定性测试",
            "verification": "翻页不重不漏",
            "evidence_fragment_ids": [],
        }
    ],
}

PROFILE_OUTPUT = {
    "identity_background": [
        {"key": "技术栈倾向", "value": "偏后端", "evidence_fragment_ids": []}
    ],
    "cognitive_style": [],
    "attention_trajectory": [],
    "high_frequency_pitfalls": [],
    "growth_signals": [],
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


async def create_report(client, headers, monkeypatch) -> dict:
    fragment_ids = await create_fragments(client, headers, monkeypatch)
    output = json.loads(json.dumps(REVIEW_OUTPUT))
    output["judgments"] = [
        {
            "fragment_id": fragment_ids[0],
            "verdict": "UNVERIFIED",
            "attribution": "VERIFICATION_MISSING",
            "reason": "结果未出现",
            "evidence_fragment_ids": [fragment_ids[0]],
        }
    ]
    output["action_items"][0]["evidence_fragment_ids"] = [fragment_ids[0]]
    patch_factory(monkeypatch, "apps.api.review.service", output)
    response = await client.post(
        "/api/v1/reviews",
        json={"period": "2026-W47", "provider": "deepseek"},
        headers=headers,
    )
    return response.json()


async def test_action_item_verify_reopen_and_cross_report_list(client, monkeypatch):
    headers = await auth_headers(client, "m9-action@x.com")
    report = await create_report(client, headers, monkeypatch)
    action = report["action_items"][0]

    verified = await client.post(
        f"/api/v1/reviews/action-items/{action['id']}/verify",
        json={"note": "已补测试"},
        headers=headers,
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "VERIFIED"
    assert verified.json()["verification_note"] == "已补测试"
    assert verified.json()["verified_at"]

    listed = await client.get(
        "/api/v1/reviews/action-items?status=VERIFIED", headers=headers
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["period"] == "2026-W47"

    reopened = await client.post(
        f"/api/v1/reviews/action-items/{action['id']}/reopen",
        json={"note": "覆盖率不够"},
        headers=headers,
    )
    assert reopened.json()["status"] == "REOPENED"
    assert reopened.json()["verified_at"] is None


async def test_review_markdown_export(client, monkeypatch):
    headers = await auth_headers(client, "m9-export@x.com")
    report = await create_report(client, headers, monkeypatch)

    response = await client.get(
        f"/api/v1/reviews/{report['id']}/export", headers=headers
    )

    assert response.status_code == 200
    assert "我的复盘记录" in response.text
    assert "补一组稳定性测试" in response.text
    assert "怎么算做到：翻页不重不漏" in response.text
    assert "提示词版本" not in response.text
    assert "模型：" not in response.text
    assert "evidence_fragment_ids" not in response.text


async def test_export_hides_technical_fields(monkeypatch):
    from datetime import UTC, datetime

    from apps.api.review.schemas import (
        ActionItemResponse,
        ReviewItemResponse,
        ReviewReportResponse,
    )
    from apps.api.review.service import review_service

    report = ReviewReportResponse(
        id=1,
        user_id=1,
        period="ws-technical-period",
        status="DONE",
        overview={
            "dialogue_count": 12,
            "domain_distribution": [{"domain": "工程实践", "count": 5}],
            "investment_distribution": [],
            "comparison_with_last_period": "比上一段更聚焦",
        },
        prompt_version="review-v1",
        model="fake-model",
        provider="deepseek",
        created_at=datetime(2026, 11, 18, tzinfo=UTC),
        items=[
            ReviewItemResponse(
                id=1,
                section="key_event",
                fragment_id=7,
                evidence_fragment_ids=[7],
                payload={
                    "fragment_id": 7,
                    "background": "翻页重排",
                    "my_judgment": "先改索引",
                    "actual_outcome": "还是会重复",
                },
            ),
            ReviewItemResponse(
                id=2,
                section="judgment",
                verdict="PARTIAL",
                attribution="VERIFICATION_MISSING",
                fragment_id=7,
                evidence_fragment_ids=[7],
                payload={"reason": "没跑回归"},
            ),
        ],
        action_items=[
            ActionItemResponse(
                id=1,
                report_id=1,
                content="补一组稳定性测试",
                verification="翻页不重不漏",
                evidence_fragment_ids=[7],
            )
        ],
    )

    async def fake_get_report(session, user_id, report_id):
        return report

    monkeypatch.setattr(review_service, "get_report", fake_get_report)
    text = await review_service.export_report_markdown(None, 1, 1)

    assert "# 我的复盘记录" in text
    assert "翻页重排" in text
    assert "有对有偏" in text
    assert "少了验证这一步" in text
    assert "怎么算做到：翻页不重不漏" in text
    for hidden in (
        "review-v1",
        "fake-model",
        "deepseek",
        "ws-technical-period",
        "VERIFICATION_MISSING",
        "fragment_id",
        "evidence_fragment_ids",
    ):
        assert hidden not in text


def test_profile_display_values_are_human_readable():
    from apps.api.profile.schemas import ProfileGroup
    from apps.api.profile.service import _display_claim_value

    assert (
        _display_claim_value(ProfileGroup.ATTENTION_TRAJECTORY.value, "product", "count=2")
        == "产品与选题：最近提到 2 次"
    )
    assert (
        _display_claim_value(ProfileGroup.HIGH_FREQUENCY_PITFALLS.value, "漏验证", "count=3")
        == "漏验证：出现过 3 次"
    )
    assert _display_claim_value(ProfileGroup.GROWTH_SIGNALS.value, "已读", "已读") is None
    assert _display_claim_value(ProfileGroup.GROWTH_SIGNALS.value, "新增技能", "已读") == "新增技能"


def test_review_display_text_hides_internal_markers():
    from apps.api.review.service import _friendly_comparison, _friendly_text

    raw_comparison = (
        "无上一周期数据（本周期为首轮，period=ws-task-8494520-r0），"
        "当前全部 outcome_status=UNVERIFIED，样本量不足。"
    )
    cleaned_comparison = _friendly_comparison(raw_comparison)
    assert "period=" not in cleaned_comparison
    assert "outcome_status" not in cleaned_comparison
    assert "第一段记录" in cleaned_comparison

    assert "period=" not in _friendly_text("当时判断 period=ws-task-abc")
    assert "outcome_status" not in _friendly_text("尚未观察到 outcome_status=UNVERIFIED")
    assert _friendly_text("先把验证口径定下来再改") == "先把验证口径定下来再改"


async def test_profile_markdown_export(client, monkeypatch):
    headers = await auth_headers(client, "m9-profile@x.com")
    fragment_ids = await create_fragments(client, headers, monkeypatch)
    output = json.loads(json.dumps(PROFILE_OUTPUT))
    output["identity_background"][0]["evidence_fragment_ids"] = [fragment_ids[0]]
    patch_factory(monkeypatch, "apps.api.profile.service", output)
    await client.post(
        "/api/v1/profile/generate",
        json={"period": "2026-W47", "provider": "deepseek"},
        headers=headers,
    )

    response = await client.get(
        "/api/v1/profile/snapshot/export?period=2026-W47", headers=headers
    )

    assert response.status_code == 200
    assert "Cairn 成长画像 · 2026-W47" in response.text
    assert "技术栈倾向" in response.text
