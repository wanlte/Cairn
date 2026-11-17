from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path

from apps.api.ingestion.schemas import IngestPreviewRequest, SourceType
from apps.api.ingestion.service import IngestionService

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


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


def qoder_sample() -> str:
    return (SAMPLES / "打造高收益项目_2026-11-17_13-14.md").read_text(encoding="utf-8")


def deepseek_zip_base64() -> str:
    buffer = io.BytesIO()
    payload = [
        {
            "title": "Fake DeepSeek Export",
            "messages": [
                {"role": "user", "content": "解释一下游标分页", "create_time": 1763300000000},
                {"role": "assistant", "content": "游标分页用稳定的排序键。", "create_time": 1763300001000},
            ],
        }
    ]
    import json

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("conversation.json", json.dumps(payload, ensure_ascii=False))
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_markdown_sample_snapshot_parses_turns_and_excludes_thinking():
    service = IngestionService()

    preview = service.preview(
        1,
        IngestPreviewRequest(
            source_type=SourceType.MARKDOWN,
            text=qoder_sample(),
            filename="qoder-export.md",
        ),
    )

    assert preview.title == "打造高收益项目"
    assert preview.total_turns >= 20
    assert preview.low_confidence_count == 0
    assert preview.anomalies == []
    assert all("#### Thinking" not in turn.assistant_content for turn in preview.turns)
    assert preview.turns[0].role_confidence >= 0.9


def test_link_only_samples_are_marked_as_unusable():
    service = IngestionService()

    for name in ("豆包示例.txt", "元宝示例.txt", "deepseek示例.txt"):
        preview = service.preview(
            1,
            IngestPreviewRequest(
                source_type=SourceType.TEXT,
                text=(SAMPLES / name).read_text(encoding="utf-8"),
                filename=name,
            ),
        )
        assert preview.total_turns == 0
        assert any("未配对" in item for item in preview.anomalies)


def test_deepseek_archive_collector_parses_zip_messages():
    service = IngestionService()

    preview = service.preview(
        1,
        IngestPreviewRequest(
            source_type=SourceType.DEEPSEEK_ARCHIVE,
            base64=deepseek_zip_base64(),
            filename="export.zip",
        ),
    )

    assert preview.total_turns == 1
    assert preview.turns[0].user_content == "解释一下游标分页"
    assert preview.turns[0].assistant_content == "游标分页用稳定的排序键。"
    assert preview.turns[0].time_precision == "HIGH"


async def test_api_preview_commit_correction_and_dedup(client):
    headers = await auth_headers(client, "ingestion@x.com")
    text = qoder_sample()

    preview_response = await client.post(
        "/api/v1/ingestion/preview",
        json={
            "source_type": "markdown",
            "text": text,
            "filename": "qoder-export.md",
        },
        headers=headers,
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    first_turn = preview["turns"][0]

    commit_response = await client.post(
        "/api/v1/ingestion/commit",
        json={
            "preview_id": preview["preview_id"],
            "corrections": [
                {
                    "turn_id": first_turn["turn_id"],
                    "user_content": "我现在想做一个能赚钱的项目",
                }
            ],
        },
        headers=headers,
    )
    assert commit_response.status_code == 200
    result = commit_response.json()
    assert result["duplicate"] is False
    assert result["turn_count"] == preview["total_turns"]

    detail = await client.get(
        f"/api/v1/ingestion/conversations/{result['conversation_id']}",
        headers=headers,
    )
    assert detail.status_code == 200
    turns = detail.json()["turns"]
    assert turns[0]["user_content"] == "我现在想做一个能赚钱的项目"
    assert turns[0]["is_corrected"] is True

    second_preview = await client.post(
        "/api/v1/ingestion/preview",
        json={"source_type": "markdown", "text": text},
        headers=headers,
    )
    duplicate = await client.post(
        "/api/v1/ingestion/commit",
        json={"preview_id": second_preview.json()["preview_id"]},
        headers=headers,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["conversation_id"] == result["conversation_id"]


async def test_preview_is_scoped_to_owner(client):
    owner = await auth_headers(client, "ingestion-owner@x.com")
    attacker = await auth_headers(client, "ingestion-attacker@x.com")
    preview_response = await client.post(
        "/api/v1/ingestion/preview",
        json={"source_type": "markdown", "text": "## 用户\nhi\n\n## 助手\nhello"},
        headers=owner,
    )
    preview = preview_response.json()

    response = await client.post(
        "/api/v1/ingestion/commit",
        json={"preview_id": preview["preview_id"]},
        headers=attacker,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PREVIEW_NOT_FOUND"
