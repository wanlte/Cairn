from __future__ import annotations

import pytest
from pydantic import SecretStr

from apps.api.credentials import service as credential_service
from apps.api.credentials.schemas import CredentialCreate
from apps.api.gateway.credential_selection import CredentialSelection
from apps.api.gateway.factory import build_gateway_for_user
from apps.api.gateway.schemas import ProviderName
from apps.api.workspace.schemas import WorkspaceModelSelection


def test_secret_str_never_serialized():
    selection = CredentialSelection(
        provider=ProviderName.DEEPSEEK,
        temporary_api_key=SecretStr("sk-super-secret-12345"),
    )
    dumped = selection.model_dump()
    assert "temporary_api_key" not in dumped
    assert "sk-super-secret-12345" not in selection.model_dump_json()
    assert "sk-super-secret-12345" not in repr(selection)


def test_workspace_selection_converts_temp_key_without_echo():
    selection = WorkspaceModelSelection(
        provider="deepseek",
        credential_mode="临时使用",
        temporary_api_key=SecretStr("sk-only-once-key"),
    )
    assert "sk-only-once-key" not in selection.model_dump_json()
    creds = selection.to_credentials()
    assert creds["provider"] == ProviderName.DEEPSEEK
    assert creds["temporary_api_key"].get_secret_value() == "sk-only-once-key"


@pytest.mark.asyncio
async def test_temp_key_overrides_saved_credential(db_session):
    saved = await credential_service.create_credential(
        db_session,
        1,
        CredentialCreate(
            name="已保存",
            provider=ProviderName.DEEPSEEK,
            api_key="sk-saved-credential-key",
            model="saved-model",
        ),
    )

    gateway, credential_id, model, provider = await build_gateway_for_user(
        db_session,
        1,
        credential_id=saved.id,
        provider=ProviderName.VOLCENGINE,
        temporary_api_key=SecretStr("sk-temporary-key"),
        temporary_base_url="https://temp.example.com/v1",
        model="temp-model",
    )

    assert credential_id is None
    assert model == "temp-model"
    assert provider == ProviderName.VOLCENGINE
    assert len(gateway.providers) == 1
    assert gateway.providers[0].api_key == "sk-temporary-key"
    assert gateway.providers[0].base_url == "https://temp.example.com/v1"


@pytest.mark.asyncio
async def test_temp_key_is_not_persisted_to_credential_table(db_session):
    from sqlalchemy import func, select

    from apps.api.db.models.credential import ModelCredential

    before = (
        await db_session.execute(select(func.count()).select_from(ModelCredential))
    ).scalar()

    await build_gateway_for_user(
        db_session,
        999,
        temporary_api_key=SecretStr("sk-never-persisted"),
        provider=ProviderName.DEEPSEEK,
    )
    await db_session.flush()

    after = (
        await db_session.execute(select(func.count()).select_from(ModelCredential))
    ).scalar()
    assert after == before
