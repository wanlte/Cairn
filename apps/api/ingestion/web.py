from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from apps.api.workspace.schemas import WorkspaceTaskCreate

_URL_RE = re.compile(r"https?://[^\s<>'\"）】]+", re.IGNORECASE)
_MAX_URLS = 3
_MAX_BYTES = 2 * 1024 * 1024
_MAX_TEXT_CHARS = 30_000
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_MAX_REDIRECTS = 3
_SKIP_TAGS = {"script", "style", "noscript", "svg", "iframe"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag.lower() in {"p", "br", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag.lower() in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def extract_urls(message: str) -> list[str]:
    """从消息里抽出 http/https 链接，去重并限制数量。"""
    urls: list[str] = []
    for match in _URL_RE.finditer(message or ""):
        candidate = match.group(0).rstrip(".,;:!?，。；：！？")
        parsed = urlparse(candidate)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            continue
        if candidate not in urls:
            urls.append(candidate)
        if len(urls) >= _MAX_URLS:
            break
    return urls


def _is_public_host(host: str) -> bool:
    """拒绝私网、回环、链路本地、云元数据等地址，降低 SSRF 风险。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - 脏 HTML 不应中断抓取
        return ""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in parser.text().splitlines()]
    text = "\n".join(line for line in lines if line)
    return text[:_MAX_TEXT_CHARS]


async def fetch_url(url: str) -> tuple[str | None, str | None]:
    """抓取链接正文。成功返回 (正文, None)，失败返回 (None, 用户提示)。"""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host:
        return None, "这个链接看起来不完整，麻烦把正文贴进来"
    if not await asyncio.to_thread(_is_public_host, host):
        return None, "这个链接地址不安全，我不能读取；麻烦把正文贴进来"

    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=True,
            max_redirects=_MAX_REDIRECTS,
            headers={"User-Agent": "Cairn/1.0 (+link reading)"},
        ) as client, client.stream("GET", url) as response:
            if response.status_code >= 400:
                return None, f"这个链接返回了 {response.status_code}，麻烦把正文贴进来"
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > _MAX_BYTES:
                    return None, "这个链接内容太长，麻烦把关键部分贴进来"
                chunks.append(chunk)
            raw = b"".join(chunks)
            content_type = response.headers.get("content-type", "").lower()
    except httpx.HTTPError:
        return None, "暂时读不到这个链接，麻烦把正文贴进来"

    if "application/json" in content_type:
        text = raw.decode("utf-8", errors="replace")[:_MAX_TEXT_CHARS]
        return text, None
    if "text/" not in content_type and "html" not in content_type:
        return None, "这个链接不是网页内容，麻烦把正文贴进来"

    html = raw.decode("utf-8", errors="replace")
    text = html_to_text(html)
    if len(text) < 20:
        return None, "这个链接没有读到可用正文（可能需要登录或脚本渲染），麻烦把正文贴进来"
    return text, None


class LinkContext(BaseModel):
    """链接抓取结果：正文直接给模型读，不走对话文件抽取链路。"""

    contents: list[str] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)

    @property
    def combined(self) -> str:
        return "\n\n".join(self.contents)


async def extract_link_context(payload: WorkspaceTaskCreate) -> LinkContext:
    """抓取消息里的链接正文；抓不到时给出明确提示，不假装分析。"""
    urls = extract_urls(payload.message)
    context = LinkContext()
    for url in urls:
        text, notice = await fetch_url(url)
        if text:
            context.contents.append(f"【链接 {url} 的正文】\n{text}")
        else:
            context.notices.append(notice or "这个链接没能读到内容，麻烦把正文贴进来")
    return context
