import asyncio
import os
import sys
from collections.abc import AsyncIterator

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from apps.api.config import get_settings
from apps.api.db.base import get_session
from apps.api.main import create_app

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _test_urls() -> tuple[str, str]:
    url = get_settings().database_url
    async_url = url.rsplit("/", 1)[0] + "/reflectai_test"
    sync_url = async_url.replace("+asyncpg", "")
    return async_url, sync_url


@pytest.fixture(scope="session")
def test_engine():
    async_url, sync_url = _test_urls()
    admin_sync = sync_url.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(admin_sync, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname='reflectai_test'"
        ).fetchone()
        if not exists:
            conn.execute("CREATE DATABASE reflectai_test")
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    previous_db_url = os.environ.get("REFLECTAI_DB_URL")
    os.environ["REFLECTAI_DB_URL"] = async_url
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous_db_url is None:
            os.environ.pop("REFLECTAI_DB_URL", None)
        else:
            os.environ["REFLECTAI_DB_URL"] = previous_db_url
    eng = create_async_engine(async_url, pool_pre_ping=True)
    yield eng
    asyncio.run(eng.dispose())


@pytest.fixture
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    async with test_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest.fixture
async def client(db_session) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
