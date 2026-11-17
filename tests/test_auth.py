async def test_register_login_refresh_flow(client):
    r = await client.post(
        "/api/v1/auth/register", json={"email": "u@x.com", "password": "password123"}
    )
    assert r.status_code == 201
    assert r.json()["email"] == "u@x.com"

    r = await client.post(
        "/api/v1/auth/login", json={"email": "u@x.com", "password": "password123"}
    )
    assert r.status_code == 200
    tokens = r.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] and tokens["refresh_token"]

    r = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_register_duplicate_email_conflict(client):
    payload = {"email": "dup@x.com", "password": "password123"}
    await client.post("/api/v1/auth/register", json=payload)
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 409
    assert r.json()["code"] == "EMAIL_EXISTS"


async def test_login_wrong_password_unauthorized(client):
    await client.post(
        "/api/v1/auth/register", json={"email": "w@x.com", "password": "password123"}
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": "w@x.com", "password": "wrongpass123"}
    )
    assert r.status_code == 401
    assert r.json()["code"] == "INVALID_CREDENTIALS"


async def test_refresh_with_access_token_rejected(client):
    await client.post(
        "/api/v1/auth/register", json={"email": "t@x.com", "password": "password123"}
    )
    tokens = (
        await client.post(
            "/api/v1/auth/login", json={"email": "t@x.com", "password": "password123"}
        )
    ).json()
    r = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert r.status_code == 401
