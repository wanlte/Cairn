from __future__ import annotations

from apps.api.ingestion.collectors import (
    DiaryCollector,
    EmailCollector,
    FeishuCollector,
    VoiceCollector,
    WechatCollector,
)
from apps.api.ingestion.schemas import IngestPreviewRequest, Role, SourceType, TimePrecision
from apps.api.ingestion.service import IngestionService


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


def wechat_sample() -> str:
    return (
        "我 2026-11-01 10:23:45\n最近在纠结要不要换研究方向\n\n"
        "张三 2026-11-01 10:24:10\n我也在想这个问题，先列证据再说"
    )


def feishu_sample() -> str:
    return (
        "[2026-11-02 09:15:00] 我: 周会改到下午了吗\n"
        "[2026-11-02 09:16:00] 李四: 改到三点，记得带复盘结论"
    )


def email_sample() -> str:
    return (
        "From: mentor@example.com\n"
        "Date: Tue, 03 Nov 2026 10:00:00 +0800\n"
        "Subject: 项目复盘\n\n"
        "这次延期主要是需求变更没对齐，下次先把验收口径写清楚。"
    )


def voice_sample() -> str:
    return "[00:00:12] 我：今天讨论一下复盘流程\n[00:01:05] 对方：好，我先说结论"


def diary_sample() -> str:
    return (
        "## 2026-11-04\n今天把证据链的实现方式想清楚了。\n\n"
        "## 2026-11-05\n和导师聊了半小时，确认先做样本体检。"
    )


def test_wechat_collector_parses_roles_and_time():
    items = WechatCollector().collect(wechat_sample())

    assert len(items) == 2
    assert items[0].role == Role.USER
    assert items[1].role == Role.ASSISTANT
    assert items[0].timestamp is not None
    assert items[0].time_precision == TimePrecision.HIGH
    assert "研究方向" in items[0].content


def test_feishu_collector_parses_bracketed_time():
    items = FeishuCollector().collect(feishu_sample())

    assert len(items) == 2
    assert items[0].role == Role.USER
    assert items[1].role == Role.ASSISTANT
    assert items[0].time_precision == TimePrecision.HIGH
    assert "复盘结论" in items[1].content


def test_email_collector_parses_headers_and_body():
    items = EmailCollector().collect(email_sample())

    assert len(items) == 1
    assert items[0].role == Role.USER
    assert items[0].time_precision == TimePrecision.HIGH
    assert items[0].metadata["subject"] == "项目复盘"
    assert "验收口径" in items[0].content


def test_voice_and_diary_collectors_keep_single_role_records():
    voice_items = VoiceCollector().collect(voice_sample())
    diary_items = DiaryCollector().collect(diary_sample())

    assert len(voice_items) == 2
    assert all(item.role == Role.USER for item in voice_items)
    assert voice_items[0].metadata["offset"] == "00:00:12"
    assert len(diary_items) == 2
    assert diary_items[0].timestamp is not None
    assert diary_items[0].time_precision == TimePrecision.HIGH


def test_preview_supports_new_sources_without_pairing():
    service = IngestionService()
    wechat = service.preview(
        1,
        IngestPreviewRequest(source_type=SourceType.WECHAT, text=wechat_sample()),
    )
    diary = service.preview(
        1,
        IngestPreviewRequest(source_type=SourceType.DIARY, text=diary_sample()),
    )

    assert wechat.total_turns == 1
    assert wechat.turns[0].role_confidence >= 0.8
    assert diary.total_turns == 2
    assert all(turn.time_precision == TimePrecision.HIGH for turn in diary.turns)


async def test_timeline_aggregates_committed_source_events(client):
    headers = await auth_headers(client, "timeline@example.com")
    preview_response = await client.post(
        "/api/v1/ingestion/preview",
        json={"source_type": "wechat", "text": wechat_sample()},
        headers=headers,
    )
    assert preview_response.status_code == 200
    preview_id = preview_response.json()["preview_id"]
    committed = await client.post(
        "/api/v1/ingestion/commit",
        json={"preview_id": preview_id, "corrections": []},
        headers=headers,
    )
    assert committed.status_code == 200

    response = await client.get("/api/v1/timeline/events", headers=headers)
    assert response.status_code == 200
    body = response.json()
    types = {item["event_type"] for item in body["items"]}
    assert "conversation" in types
    assert "turn" in types
    assert body["total"] >= 2

    filtered = await client.get(
        "/api/v1/timeline/events",
        params={"event_types": ["conversation"]},
        headers=headers,
    )
    assert filtered.status_code == 200
    assert {item["event_type"] for item in filtered.json()["items"]} == {"conversation"}
