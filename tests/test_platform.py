from __future__ import annotations


async def _register_and_login(client, email: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_api_key_scopes_and_revocation(client):
    headers = await _register_and_login(client, "platform-key@cairn.dev")
    created = await client.post(
        "/api/v1/platform/keys",
        json={"name": "笔记本插件", "scopes": ["profile:read"]},
        headers=headers,
    )
    assert created.status_code == 201
    body = created.json()
    token = body["token"]
    assert token.startswith("ck_")
    assert body["key_prefix"] == token[:16]
    assert "token" not in (await client.get("/api/v1/platform/keys", headers=headers)).json()[0]

    scoped = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/platform/keys", headers=scoped)).status_code == 200
    denied = await client.get("/api/v1/platform/pairs", headers=scoped)
    assert denied.status_code == 403
    assert denied.json()["code"] == "FORBIDDEN"

    revoked = await client.delete(f"/api/v1/platform/keys/{body['id']}", headers=headers)
    assert revoked.status_code == 204
    after = await client.get("/api/v1/platform/keys", headers=scoped)
    assert after.status_code == 401


async def test_consent_grant_and_revoke(client):
    headers = await _register_and_login(client, "platform-consent@cairn.dev")
    created = await client.post(
        "/api/v1/platform/consents",
        json={"consent_type": "platform_api", "payload": {"api_key": "should-be-hidden"}},
        headers=headers,
    )
    assert created.status_code == 201
    consent_id = created.json()["id"]
    listed = await client.get("/api/v1/platform/consents", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["granted"] is True
    assert "should-be-hidden" not in listed.text

    revoked = await client.delete(f"/api/v1/platform/consents/{consent_id}", headers=headers)
    assert revoked.status_code == 204
    listed = await client.get("/api/v1/platform/consents", headers=headers)
    assert listed.json()[0]["granted"] is False


async def test_pair_requires_counterpart_confirmation(client):
    headers_a = await _register_and_login(client, "platform-a@cairn.dev")
    headers_b = await _register_and_login(client, "platform-b@cairn.dev")
    created = await client.post(
        "/api/v1/platform/pairs",
        json={"counterpart_email": "platform-b@cairn.dev", "note": "一起做关系复盘"},
        headers=headers_a,
    )
    assert created.status_code == 201
    pair_id = created.json()["id"]
    assert created.json()["status"] == "PENDING"

    self_confirm = await client.post(f"/api/v1/platform/pairs/{pair_id}/confirm", headers=headers_a)
    assert self_confirm.status_code == 400
    confirmed = await client.post(f"/api/v1/platform/pairs/{pair_id}/confirm", headers=headers_b)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "ACTIVE"

    listed = await client.get("/api/v1/platform/pairs", headers=headers_a)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [pair_id]
    other = await client.get("/api/v1/platform/pairs", headers=headers_b)
    assert [item["id"] for item in other.json()] == [pair_id]


async def test_audit_log_records_actions_without_secrets(client):
    headers = await _register_and_login(client, "platform-audit@cairn.dev")
    await client.post(
        "/api/v1/platform/keys",
        json={"name": "审计测试", "scopes": ["profile:read"], "expires_in_days": 3},
        headers=headers,
    )
    logs = await client.get("/api/v1/platform/audit", headers=headers)
    assert logs.status_code == 200
    body = logs.text
    assert "api_key.created" in body
    assert "ck_" not in body
