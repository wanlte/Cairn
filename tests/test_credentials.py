from __future__ import annotations

from sqlalchemy import select

from apps.api.credentials.service import decrypt_api_key
from apps.api.db.models.credential import ModelCredential
from apps.api.gateway.capabilities import KNOWN_CAPABILITIES
from apps.api.gateway.schemas import ProviderName, ResponseFormat


async def auth_headers(client, email: str) -> dict[str, str]:
    password = "password123"
    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


CONFIRM = {"X-Confirm-Action": "confirm"}


async def test_create_credential_encrypts_key_and_masks_response(client, db_session):
    headers = await auth_headers(client, "cred-a@x.com")
    payload = {
        "name": "my-deepseek",
        "provider": "deepseek",
        "api_key": "sk-secret12345678",
        "model": "deepseek-chat",
    }

    response = await client.post(
        "/api/v1/credentials", json=payload, headers={**headers, **CONFIRM}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["api_key_masked"] == "sk-****5678"
    assert "sk-secret12345678" not in str(body)

    row = (
        await db_session.execute(
            select(ModelCredential).where(ModelCredential.id == body["id"])
        )
    ).scalar_one()
    assert "sk-secret12345678" not in row.api_key_encrypted
    assert decrypt_api_key(row.api_key_encrypted) == "sk-secret12345678"

    listed = await client.get("/api/v1/credentials", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["api_key_masked"] == "sk-****5678"


async def test_credential_mutations_require_confirmation(client):
    headers = await auth_headers(client, "cred-b@x.com")
    payload = {
        "name": "needs-confirm",
        "provider": "openai_compat",
        "api_key": "sk-confirm-me-1234",
        "base_url": "https://example.com/v1",
        "model": "local-model",
    }

    response = await client.post("/api/v1/credentials", json=payload, headers=headers)

    assert response.status_code == 428
    assert response.json()["code"] == "CONFIRMATION_REQUIRED"


async def test_credential_test_probes_and_caches_capabilities(client, monkeypatch):
    headers = await auth_headers(client, "cred-c@x.com")
    created = await client.post(
        "/api/v1/credentials",
        json={
            "name": "compat",
            "provider": "openai_compat",
            "api_key": "sk-probe-1234",
            "base_url": "https://example.com/v1",
            "model": "local-model",
        },
        headers={**headers, **CONFIRM},
    )
    credential_id = created.json()["id"]

    async def fake_probe(provider):
        capabilities = KNOWN_CAPABILITIES[provider.name].model_copy(deep=True)
        capabilities.json_schema = True
        capabilities.structured_output = ResponseFormat.JSON_SCHEMA
        capabilities.probed = True
        return capabilities

    monkeypatch.setattr(
        "apps.api.credentials.router.probe_capabilities", fake_probe
    )
    tested = await client.post(
        f"/api/v1/credentials/{credential_id}/test", headers=headers
    )

    assert tested.status_code == 200
    assert tested.json()["capabilities"]["json_schema"] is True
    capabilities = await client.get(
        "/api/v1/credentials/capabilities", headers=headers
    )
    assert capabilities.status_code == 200
    assert any(
        item.get("credential_id") == credential_id
        for item in capabilities.json()["probed"]
    )


async def test_user_cannot_delete_another_users_credential(client):
    owner = await auth_headers(client, "cred-owner@x.com")
    attacker = await auth_headers(client, "cred-attacker@x.com")
    created = await client.post(
        "/api/v1/credentials",
        json={
            "name": "private",
            "provider": ProviderName.DEEPSEEK.value,
            "api_key": "sk-private-key-1234",
        },
        headers={**owner, **CONFIRM},
    )
    credential_id = created.json()["id"]

    response = await client.delete(
        f"/api/v1/credentials/{credential_id}",
        headers={**attacker, **CONFIRM},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "CREDENTIAL_NOT_FOUND"
