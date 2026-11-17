from httpx import ASGITransport, AsyncClient

from apps.api.errors import AppError
from apps.api.main import create_app


async def test_app_error_unified_body():
    app = create_app()

    @app.get("/api/v1/_boom")
    async def boom():
        raise AppError("RATE_LIMIT", "太频繁", 429, retryable=True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/_boom")
    assert r.status_code == 429
    body = r.json()
    assert body["code"] == "RATE_LIMIT"
    assert body["retryable"] is True
    assert "request_id" in body and "message" in body


async def test_validation_error_unified_body(client):
    r = await client.post("/api/v1/auth/register", json={"email": "not-an-email"})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"
    assert "request_id" in r.json()
