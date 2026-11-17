import httpx
import pytest

from apps.api.main import create_app


@pytest.fixture
def app():
    return create_app()


async def test_health_ok_and_request_id_header(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers.get("X-Request-ID")


async def test_request_id_echoes_incoming(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health", headers={"X-Request-ID": "fixed-id-123"})
    assert resp.headers["X-Request-ID"] == "fixed-id-123"
