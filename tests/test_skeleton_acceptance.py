async def test_full_auth_flow_with_request_id(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "accept@x.com", "password": "password123"},
        headers={"X-Request-ID": "accept-rid-001"},
    )
    assert r.status_code == 201
    assert r.headers["X-Request-ID"] == "accept-rid-001"

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "accept@x.com", "password": "password123"},
    )
    assert r.status_code == 200
    access = r.json()["access_token"]

    r = await client.get("/api/v1/health", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_unauthorized_error_body_has_request_id(client):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@x.com", "password": "password123"}
    )
    assert r.status_code == 401
    body = r.json()
    assert set(body) >= {"code", "message", "request_id", "retryable"}
