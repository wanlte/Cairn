import asyncpg
import pytest
import redis.asyncio as aioredis


async def test_postgres_reachable_and_pgvector_available():
    conn = await asyncpg.connect(
        "postgresql://reflectai:reflectai@127.0.0.1:5433/reflectai"
    )
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        row = await conn.fetchval("SELECT extname FROM pg_extension WHERE extname='vector'")
        assert row == "vector"
    finally:
        await conn.close()


async def test_redis_reachable():
    client = aioredis.from_url("redis://localhost:6379/0")
    try:
        assert await client.ping() is True
    finally:
        await client.aclose()
