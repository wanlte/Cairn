from __future__ import annotations

import pytest

from apps.api.ingestion.web import (
    extract_link_context,
    extract_urls,
    fetch_url,
    html_to_text,
)
from apps.api.workspace.schemas import WorkspaceTaskCreate


def test_extract_urls_and_clean_text():
    urls = extract_urls("看看 https://example.com/a?x=1 ，还有 https://example.org/b。")
    assert urls == ["https://example.com/a?x=1", "https://example.org/b"]
    assert extract_urls("没有链接") == []

    text = html_to_text(
        "<html><head><style>hidden</style></head><body><h1>标题</h1>"
        "<p>这是第一段正文内容，足够长可以通过检查。</p>"
        "<script>不该出现</script></body></html>"
    )
    assert "标题" in text
    assert "第一段正文内容" in text
    assert "不该出现" not in text


@pytest.mark.asyncio
async def test_private_host_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "apps.api.ingestion.web._is_public_host", lambda host: host == "example.com"
    )
    text, notice = await fetch_url("http://127.0.0.1/secret")
    assert text is None
    assert "不安全" in (notice or "")


@pytest.mark.asyncio
async def test_extract_link_context_returns_body(monkeypatch):
    async def fake_fetch(url):
        return "这是链接里读到的真实正文内容。" * 3, None

    monkeypatch.setattr("apps.api.ingestion.web.fetch_url", fake_fetch)
    payload = WorkspaceTaskCreate(message="帮我看看 https://example.com/share")
    context = await extract_link_context(payload)
    assert context.notices == []
    assert "https://example.com/share" in context.combined
    assert "真实正文" in context.combined


@pytest.mark.asyncio
async def test_extract_link_context_reports_failure(monkeypatch):
    async def fake_fetch(url):
        return None, "这个链接没有读到可用正文，麻烦把正文贴进来"

    monkeypatch.setattr("apps.api.ingestion.web.fetch_url", fake_fetch)
    payload = WorkspaceTaskCreate(message="https://example.com/share")
    context = await extract_link_context(payload)
    assert context.combined == ""
    assert context.notices
    assert "贴进来" in context.notices[0]
