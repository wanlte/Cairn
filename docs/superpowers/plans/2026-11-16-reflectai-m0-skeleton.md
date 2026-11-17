# ReflectAI M0 骨架与基础设施 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭起 ReflectAI 的可运行地基——Docker Compose 一键起 PostgreSQL/pgvector/Redis，FastAPI 应用带配置、结构化日志、request_id 全链路、异步 DB 与迁移、JWT 鉴权、统一错误体，为后续网关与业务层提供稳定底座。

**Architecture:** 单仓 monorepo（`apps/api` 后端，`apps/web` 前端后置）。后端 FastAPI 应用工厂 + pydantic-settings 配置 + structlog JSON 日志 + SQLAlchemy 2.0 async + Alembic 迁移。鉴权 JWT（access 2h / refresh 7d），密码 pwdlib argon2 哈希。所有表带 `user_id` 多租户就绪。测试用 compose 起的真实 PG（独立 test 库 + 事务回滚），不 mock 数据库。

**Tech Stack:** Python 3.11+ · FastAPI · SQLAlchemy 2.0 (async) · asyncpg · psycopg · Alembic · PostgreSQL 16 (pgvector) · Redis 7 · pydantic-settings · structlog · PyJWT · pwdlib[argon2] · cryptography · uv · pytest · ruff · Docker Compose

**Spec:** `docs/superpowers/specs/2026-11-16-reflectai-agent-layer-design.md`（agent 层设计，本计划为其地基）；上游 `AI对话复盘助手_PRD_v2.md` v2.1（M0 章节、8.2 数据原则、9.1/9.3 API 与鉴权、11 NFR、12.2 安全红线）

## Global Constraints

- Python 3.11+；PostgreSQL 14+（用 pgvector/pgvector:pg16）；Redis 7。
- 后端 FastAPI + SQLAlchemy 2.0 (async) + Alembic；依赖管理 uv；lint ruff（line-length 100, target py311）；测试 pytest（asyncio_mode=auto）。
- API 前缀 `/api/v1`；统一错误体 `{"code","message","request_id","retryable"}`；游标分页 `cursor`+`limit`；写接口支持 `Idempotency-Key` 头（本计划仅约定，后续计划落地）。
- 鉴权 JWT：access 2h / refresh 7d；密码哈希用 pwdlib argon2，不明文存储。
- 密钥用 `cryptography.fernet` 加密，主密钥来自环境变量 `REFLECTAI_SECRET_KEY`；**不明文落库、不出现在日志与响应中**；含密钥响应一律掩码 `sk-****abcd`（本计划先建日志过滤与配置，凭证接口在 Plan 2）。
- 结构化日志 JSON + `request_id` 全链路；日志过滤器屏蔽 `sk-` 模式与对话原文。
- 所有业务表带 `user_id`（多租户就绪，即便当前单用户）。
- CORS 默认仅 `127.0.0.1`（前端 dev `http://127.0.0.1:5173`）。
- `docker compose up` 一键起基础设施；提供 `.env.example`；`.gitignore` 覆盖 `.env`。
- 业务层永不 import 厂商 SDK；模型调用唯一入口 `ModelGateway.complete`（Plan 2 落地，本计划不涉及模型调用）。
-  frequent commits：每个 Task 结束提交一次；commit message 用 conventional commits（feat/fix/test/chore）。
- 前置工具（需工程师自行安装，不自动装系统依赖）：Python 3.11+、uv（astral.sh/uv）、Docker Desktop（含 compose）、Git。

## File Structure

| 路径 | 职责 |
|---|---|
| `pyproject.toml` | 依赖、ruff/pytest 配置、打包 |
| `.gitignore` / `.env.example` / `README.md` | 仓库卫生与启动说明 |
| `docker-compose.yml` | postgres(pgvector) + redis + healthcheck |
| `alembic.ini` / `apps/api/db/migrations/` | 迁移配置与脚本 |
| `apps/api/config.py` | pydantic-settings 配置 |
| `apps/api/logging.py` | structlog JSON 日志 + sk- 过滤 + request_id contextvar |
| `apps/api/middleware.py` | request_id 中间件 |
| `apps/api/errors.py` | AppError + 统一错误体 + 异常处理器 |
| `apps/api/db/base.py` | DeclarativeBase + async engine/session + get_session |
| `apps/api/db/models/user.py` | User 模型 |
| `apps/api/auth/{schemas,service,deps,router}.py` | 鉴权 schemas/服务/依赖/路由 |
| `apps/api/health.py` | 健康检查 |
| `apps/api/main.py` | 应用工厂 create_app |
| `tests/conftest.py` | test 库 + 事务回滚 + client fixtures |
| `tests/test_*.py` | 各 Task 测试 |

---

### Task 1: 仓库初始化与项目骨架

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, `apps/__init__.py`, `apps/api/__init__.py`, `apps/api/main.py`, `tests/__init__.py`, `tests/test_smoke.py`

**Interfaces:**
- Consumes: 无（首个 Task）
- Produces: `apps.api.main.create_app() -> FastAPI`（后续 Task 扩展）；包路径 `apps.api.*`；命令 `uv sync` / `uv run pytest` / `uv run ruff check`。

- [ ] **Step 1: 初始化 git 与目录**

仓库根：`F:/work/new`。按当前终端选一条执行。

PowerShell（Windows）：
```powershell
git init
New-Item -ItemType Directory -Force -Path apps/api/db/models, apps/api/auth, tests
@(
  'apps/__init__.py',
  'apps/api/__init__.py',
  'apps/api/db/__init__.py',
  'apps/api/db/models/__init__.py',
  'apps/api/auth/__init__.py',
  'tests/__init__.py'
) | ForEach-Object { New-Item -ItemType File -Force -Path $_ }
```

Git Bash / Linux / macOS：
```bash
git init
mkdir -p apps/api/db/models apps/api/auth tests
touch apps/__init__.py apps/api/__init__.py apps/api/db/__init__.py apps/api/db/models/__init__.py apps/api/auth/__init__.py tests/__init__.py
```

- [ ] **Step 2: 写 `.gitignore`**

```gitignore
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
dist/
*.egg-info/
.coverage
htmlcov/
node_modules/
apps/web/dist/
```

- [ ] **Step 3: 写 `pyproject.toml`**

```toml
[project]
name = "reflectai-api"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.7",
  "pydantic-settings>=2.3",
  "sqlalchemy[asyncio]>=2.0.30",
  "asyncpg>=0.29",
  "psycopg[binary]>=3.1",
  "alembic>=1.13",
  "pgvector>=0.2.5",
  "redis>=5.0",
  "structlog>=24.1",
  "pyjwt>=2.8",
  "pwdlib[argon2]>=0.2",
  "python-multipart>=0.0.9",
  "cryptography>=42.0",
  "email-validator>=2.1",
]

[dependency-groups]
dev = [
  "pytest>=8.2",
  "pytest-asyncio>=0.23",
  "httpx>=0.27",
  "ruff>=0.4",
  "detect-secrets>=1.4",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
ignore = ["B008"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["apps/api"]
```

- [ ] **Step 4: 写 `.env.example`**

```dotenv
ENVIRONMENT=dev
DATABASE_URL=postgresql+asyncpg://reflectai:reflectai@127.0.0.1:5433/reflectai
REDIS_URL=redis://localhost:6379/0
REFLECTAI_SECRET_KEY=change-me-to-a-long-random-secret-value
JWT_SECRET=change-me-jwt-secret
JWT_ACCESS_TTL_MINUTES=120
JWT_REFRESH_TTL_DAYS=7
CORS_ORIGINS=["http://127.0.0.1:5173"]
```

- [ ] **Step 5: 写最小应用工厂 `apps/api/main.py`**

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="ReflectAI API", version="0.1.0")
    return app
```

- [ ] **Step 6: 写冒烟测试 `tests/test_smoke.py`**

```python
from fastapi import FastAPI

from apps.api.main import create_app


def test_create_app_returns_fastapi():
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "ReflectAI API"
```

- [ ] **Step 7: 安装依赖并跑测试验证通过**

Run:
```bash
uv sync
uv run pytest tests/test_smoke.py -v
```
Expected: PASS（1 passed）。若 uv 未安装，先按 astral.sh/uv 安装。

- [ ] **Step 8: 写 README 启动 stub**

````markdown
# ReflectAI

多平台 AI 对话复盘与成长档案系统（个人开源项目）。

## 状态
M0 骨架进行中。架构见 `docs/superpowers/specs/`，需求见 `AI对话复盘助手_PRD_v2.md`。

## 快速开始
前置：Python 3.11+、uv、Docker Desktop、Git。
```bash
cp .env.example .env
uv sync
docker compose up -d
uv run pytest
```
````

- [ ] **Step 9: lint 并提交**

Run:
```bash
uv run ruff check .
git add .gitignore pyproject.toml .env.example README.md apps tests
git commit -m "chore: scaffold repo, deps, app factory and smoke test"
```

---

### Task 2: Docker Compose 基础设施

**Files:**
- Create: `docker-compose.yml`, `tests/test_infra.py`

**Interfaces:**
- Consumes: `.env.example`（Task 1）的 DATABASE_URL/REDIS_URL 默认值。
- Produces: 运行中的 postgres（库 `reflectai`，用户/密码 `reflectai`，宿主机端口 5433 映射容器 5432，含 pgvector 扩展）与 redis（端口 6379）；后续所有 DB 测试依赖 `docker compose up -d`。若宿主 5432 空闲，也可改回 `5432:5432` 并同步连接串。

- [ ] **Step 1: 写 `docker-compose.yml`**

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: reflectai
      POSTGRES_PASSWORD: reflectai
      POSTGRES_DB: reflectai
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U reflectai"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - pgdata:/var/lib/postgresql/data
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
volumes:
  pgdata:
```

- [ ] **Step 2: 起服务并确认健康**

Run:
```bash
cp .env.example .env
docker compose up -d
docker compose ps
```
Expected: postgres 与 redis 状态 `(healthy)`。

- [ ] **Step 3: 写基础设施连通测试 `tests/test_infra.py`**

```python
import asyncpg
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
```

- [ ] **Step 4: 跑测试验证通过**

Run: `uv run pytest tests/test_infra.py -v`
Expected: PASS（2 passed）。若失败先确认 `docker compose ps` 健康。

- [ ] **Step 5: 提交**

```bash
git add docker-compose.yml tests/test_infra.py
git commit -m "feat: docker compose postgres(pgvector)+redis with connectivity tests"
```

---

### Task 3: 配置、结构化日志与 request_id 中间件

**Files:**
- Create: `apps/api/config.py`, `apps/api/logging.py`, `apps/api/middleware.py`, `apps/api/errors.py`, `apps/api/health.py`, `tests/test_health.py`
- Modify: `apps/api/main.py`

**Interfaces:**
- Consumes: `create_app`（Task 1）。
- Produces:
  - `apps.api.config.get_settings() -> Settings`（lru_cache 单例）；`Settings` 字段：`environment, database_url, redis_url, reflectai_secret_key, jwt_secret, jwt_access_ttl_minutes, jwt_refresh_ttl_days, cors_origins`。
  - `apps.api.logging.setup_logging() -> None`；`apps.api.logging.request_id_var: ContextVar[str]`；`get_logger()`。
  - `apps.api.middleware.RequestIdMiddleware`（每请求生成 uuid4，写 contextvar，响应头 `X-Request-ID`）。
  - `apps.api.errors.AppError(code: str, message: str, status_code: int = 400, retryable: bool = False)`；`apps.api.errors.register_error_handlers(app) -> None`（本 Task 仅装 AppError 处理器；校验/未捕获处理器在 Task 6 补齐）。
  - `apps.api.health.router`（`GET /api/v1/health`）。

- [ ] **Step 1: 写配置 `apps/api/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "dev"
    database_url: str = "postgresql+asyncpg://reflectai:reflectai@127.0.0.1:5433/reflectai"
    redis_url: str = "redis://localhost:6379/0"
    reflectai_secret_key: str = "dev-insecure-change-me"
    jwt_secret: str = "dev-jwt-insecure-change-me"
    jwt_access_ttl_minutes: int = 120
    jwt_refresh_ttl_days: int = 7
    cors_origins: list[str] = ["http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 2: 写日志 `apps/api/logging.py`**

```python
import logging
import re
from contextvars import ContextVar

import structlog

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]+")


def _redact_secrets(logger, method_name, event_dict):
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = _SK_PATTERN.sub("sk-****", value)
    return event_dict


def _add_request_id(logger, method_name, event_dict):
    event_dict.setdefault("request_id", request_id_var.get())
    return event_dict


def setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_request_id,
            _redact_secrets,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger():
    return structlog.get_logger()
```

- [ ] **Step 3: 写中间件 `apps/api/middleware.py`**

```python
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from apps.api.logging import request_id_var


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response
```

- [ ] **Step 4: 写健康检查 `apps/api/health.py`**

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 5: 写失败测试 `tests/test_health.py`**

```python
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
```

- [ ] **Step 6: 跑测试验证失败**

Run: `uv run pytest tests/test_health.py -v`
Expected: FAIL（404，路由/中间件未装配）。

- [ ] **Step 7: 写错误模块基础版 `apps/api/errors.py`（仅 AppError 处理器）**

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from apps.api.logging import request_id_var


class AppError(Exception):
    def __init__(
        self, code: str, message: str, status_code: int = 400, retryable: bool = False
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)


def _body(code: str, message: str, retryable: bool) -> dict:
    return {
        "code": code,
        "message": message,
        "request_id": request_id_var.get(),
        "retryable": retryable,
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.retryable),
        )
```

- [ ] **Step 8: 装配应用 `apps/api/main.py`（整文件替换）**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import get_settings
from apps.api.errors import register_error_handlers
from apps.api.health import router as health_router
from apps.api.logging import setup_logging
from apps.api.middleware import RequestIdMiddleware


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(title="ReflectAI API", version="0.1.0")
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    register_error_handlers(app)
    return app
```

- [ ] **Step 9: 跑测试验证通过**

Run: `uv run pytest tests/test_health.py tests/test_smoke.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 10: 提交**

```bash
git add apps/api/config.py apps/api/logging.py apps/api/middleware.py apps/api/errors.py apps/api/health.py apps/api/main.py tests/test_health.py
git commit -m "feat: settings, structlog logging, request_id middleware, AppError, health"
```

---

### Task 4: 异步数据库基线与 User 迁移

**Files:**
- Create: `apps/api/db/base.py`, `apps/api/db/models/user.py`, `alembic.ini`, `apps/api/db/migrations/env.py`, `apps/api/db/migrations/script.py.mako`, `tests/conftest.py`, `tests/test_db.py`
- Modify: `apps/api/db/models/__init__.py`

**Interfaces:**
- Consumes: `get_settings()`（Task 3）；compose postgres（Task 2）。
- Produces:
  - `apps.api.db.base.Base`（DeclarativeBase）；`engine`（AsyncEngine）；`SessionLocal`（async_sessionmaker）；`async get_session() -> AsyncIterator[AsyncSession]`（FastAPI 依赖）。
  - `apps.api.db.models.user.User`：`id: int`(BIGSERIAL PK), `email: str`(unique), `password_hash: str`, `created_at: datetime`。
  - `tests/conftest.py` fixtures：`test_engine`（session 级，独立 `reflectai_test` 库 + alembic upgrade）、`db_session`（每测试事务回滚）、`client`（ASGITransport + 覆盖 get_session）。

- [ ] **Step 1: 写 DB 基座 `apps/api/db/base.py`**

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from apps.api.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 2: 写 User 模型 `apps/api/db/models/user.py`**

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 3: 导出模型 `apps/api/db/models/__init__.py`（整文件替换）**

```python
from apps.api.db.models.user import User

__all__ = ["User"]
```

- [ ] **Step 4: 初始化 Alembic**

Run:
```bash
uv run alembic init apps/api/db/migrations
```
然后整文件替换 `alembic.ini` 中 `script_location` 与 `sqlalchemy.url` 两行：
```ini
script_location = apps/api/db/migrations
sqlalchemy.url = postgresql+psycopg://reflectai:reflectai@127.0.0.1:5433/reflectai
```

- [ ] **Step 5: 写异步迁移环境 `apps/api/db/migrations/env.py`（整文件替换）**

```python
import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from apps.api.config import get_settings
from apps.api.db.base import Base
from apps.api.db import models  # noqa: F401  确保模型注册

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url",
    os.getenv("REFLECTAI_DB_URL") or get_settings().database_url,
)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 6: 生成并应用首个迁移**

Run:
```bash
uv run alembic revision --autogenerate -m "create users"
uv run alembic upgrade head
```
Expected: 生成 `apps/api/db/migrations/versions/xxxx_create_users.py`，upgrade 成功，`users` 表存在。

- [ ] **Step 7: 写测试 fixtures `tests/conftest.py`**

```python
import asyncio
import os
import sys
from collections.abc import AsyncIterator

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

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
    eng = create_async_engine(async_url, pool_pre_ping=True, poolclass=NullPool)
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
```

- [ ] **Step 8: 写 DB 测试 `tests/test_db.py`**

```python
from sqlalchemy import select

from apps.api.db.models.user import User


async def test_user_roundtrip(db_session):
    user = User(email="a@b.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    assert user.id is not None
    result = await db_session.execute(select(User).where(User.email == "a@b.com"))
    fetched = result.scalar_one()
    assert fetched.id == user.id
```

- [ ] **Step 9: 跑测试验证通过**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS（1 passed）。需要 `docker compose up -d` 已起。

- [ ] **Step 10: 提交**

```bash
git add apps/api/db alembic.ini tests/conftest.py tests/test_db.py
git commit -m "feat: async db base, User model, alembic migration, test db fixtures"
```

---

### Task 5: JWT 鉴权（注册/登录/刷新）

**Files:**
- Create: `apps/api/auth/schemas.py`, `apps/api/auth/service.py`, `apps/api/auth/deps.py`, `apps/api/auth/router.py`, `tests/test_auth.py`
- Modify: `apps/api/main.py`

**Interfaces:**
- Consumes: `get_session`（Task 4）、`User`（Task 4）、`get_settings()`（Task 3）、`client`/`db_session` fixtures（Task 4）。
- Produces:
  - `apps.api.auth.service`：`hash_password(pw: str) -> str`；`verify_password(pw: str, hashed: str) -> bool`；`create_access_token(user_id: int) -> str`；`create_refresh_token(user_id: int) -> str`；`decode_token(token: str) -> dict`（含 `sub`,`type`,`exp`）；`async register_user(session, email, password) -> User`；`async login_user(session, email, password) -> tuple[str, str]`；`async refresh_tokens(session, refresh_token) -> tuple[str, str]`。
  - `apps.api.auth.deps.get_current_user`（FastAPI 依赖，Bearer access token → User）。
  - `apps.api.auth.router`：`POST /api/v1/auth/register`（201）、`/login`（200）、`/refresh`（200）。
  - schemas：`RegisterRequest{email,password}`、`LoginRequest{email,password}`、`RefreshRequest{refresh_token}`、`TokenResponse{access_token,refresh_token,token_type="bearer"}`、`UserResponse{id,email}`。

- [ ] **Step 1: 写 schemas `apps/api/auth/schemas.py`**

```python
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: EmailStr
```

注意：`EmailStr` 需要 `email-validator`，已在 Task 1 的 `pyproject.toml` 中声明；直接 `uv sync` 即可，无需再改依赖。

- [ ] **Step 2: 写失败测试 `tests/test_auth.py`**

```python
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
```

- [ ] **Step 3: 跑测试验证失败**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL（404，路由未实现）。

- [ ] **Step 4: 写服务 `apps/api/auth/service.py`**

```python
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.db.models.user import User
from apps.api.errors import AppError

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)


def _create_token(user_id: int, token_type: str, expires: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "type": token_type, "iat": now, "exp": now + expires}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_access_token(user_id: int) -> str:
    return _create_token(
        user_id, "access", timedelta(minutes=get_settings().jwt_access_ttl_minutes)
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        user_id, "refresh", timedelta(days=get_settings().jwt_refresh_ttl_days)
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise AppError("INVALID_TOKEN", "令牌无效或已过期", 401, retryable=False) from e


async def register_user(session: AsyncSession, email: str, password: str) -> User:
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing:
        raise AppError("EMAIL_EXISTS", "邮箱已注册", 409, retryable=False)
    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    await session.flush()
    return user


async def login_user(session: AsyncSession, email: str, password: str) -> tuple[str, str]:
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "邮箱或密码错误", 401, retryable=False)
    return create_access_token(user.id), create_refresh_token(user.id)


async def refresh_tokens(session: AsyncSession, refresh_token: str) -> tuple[str, str]:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise AppError("INVALID_TOKEN", "需要 refresh 令牌", 401, retryable=False)
    user = await session.get(User, int(payload["sub"]))
    if not user:
        raise AppError("INVALID_TOKEN", "用户不存在", 401, retryable=False)
    return create_access_token(user.id), create_refresh_token(user.id)
```

- [ ] **Step 5: 写依赖 `apps/api/auth/deps.py`**

```python
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.service import decode_token
from apps.api.db.base import get_session
from apps.api.db.models.user import User
from apps.api.errors import AppError

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if creds is None:
        raise AppError("UNAUTHORIZED", "缺少令牌", 401, retryable=False)
    payload = decode_token(creds.credentials)
    if payload.get("type") != "access":
        raise AppError("INVALID_TOKEN", "需要 access 令牌", 401, retryable=False)
    user = await session.get(User, int(payload["sub"]))
    if not user:
        raise AppError("UNAUTHORIZED", "用户不存在", 401, retryable=False)
    return user
```

- [ ] **Step 6: 写路由 `apps/api/auth/router.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import service
from apps.api.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from apps.api.db.base import get_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    user = await service.register_user(session, body.email, body.password)
    await session.commit()
    return UserResponse(id=user.id, email=user.email)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    access, refresh = await service.login_user(session, body.email, body.password)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)):
    access, new_refresh = await service.refresh_tokens(session, body.refresh_token)
    return TokenResponse(access_token=access, refresh_token=new_refresh)
```

- [ ] **Step 7: 装配路由（修改 `apps/api/main.py`）**

`register_error_handlers`（含 AppError 处理器）已在 Task 3 Step 8 装配，本步骤只需挂鉴权路由，无跨任务依赖。

在 `from apps.api.health import router as health_router` 后加：
```python
from apps.api.auth.router import router as auth_router
```
在 `app.include_router(health_router)` 后加：
```python
    app.include_router(auth_router)
```

- [ ] **Step 8: 跑测试验证通过**

Run: `uv run pytest tests/test_auth.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 9: 提交**

```bash
git add apps/api/auth apps/api/main.py pyproject.toml tests/test_auth.py
git commit -m "feat: JWT auth register/login/refresh with argon2 hashing"
```

---

### Task 6: 补齐校验与未捕获异常处理器

`apps/api/errors.py` 的基础版（AppError + 其处理器）已在 Task 3 落地并被 main.py 装配。本 Task 以测试先行补齐 `RequestValidationError` 与未捕获 `Exception` 两个处理器，使**所有**错误响应都收敛到统一错误体。无跨任务跳转。

**Files:**
- Modify: `apps/api/errors.py`（整文件替换为最终版）
- Create: `tests/test_errors.py`

**Interfaces:**
- Consumes: `AppError` / `register_error_handlers` / `request_id_var`（Task 3）；`/api/v1/auth/register` 路由与 `client` fixture（Task 4/5，用于触发校验错误）。
- Produces: `apps.api.errors.register_error_handlers(app: FastAPI) -> None` 最终版——处理 `AppError`、`RequestValidationError`、未捕获 `Exception`，统一返回 `{"code","message","request_id","retryable"}`。main.py 无需改动（Task 3 已调用该函数，替换模块即生效）。

- [ ] **Step 1: 写失败测试 `tests/test_errors.py`**

```python
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
```

- [ ] **Step 2: 跑测试验证失败**

Run: `uv run pytest tests/test_errors.py -v`
Expected: `test_app_error_unified_body` PASS（Task 3 已装 AppError 处理器）；`test_validation_error_unified_body` FAIL——FastAPI 默认 422 返回 `{"detail":[...]}`，无 `code` 字段，断言抛 `KeyError: 'code'`。这正是本 Task 要修的红。

- [ ] **Step 3: 替换错误模块为最终版 `apps/api/errors.py`（整文件替换）**

```python
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from apps.api.logging import get_logger, request_id_var

logger = get_logger()


class AppError(Exception):
    def __init__(
        self, code: str, message: str, status_code: int = 400, retryable: bool = False
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)


def _body(code: str, message: str, retryable: bool) -> dict:
    return {
        "code": code,
        "message": message,
        "request_id": request_id_var.get(),
        "retryable": retryable,
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.retryable),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_body("VALIDATION_ERROR", "请求参数校验失败", False),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=_body("INTERNAL_ERROR", "服务内部错误", True),
        )
```

- [ ] **Step 4: 跑测试验证通过（含鉴权回归）**

Run: `uv run pytest tests/test_errors.py tests/test_auth.py -v`
Expected: PASS（6 passed）。main.py 无需改动——Task 3 已调用 `register_error_handlers`，替换模块后校验/未捕获处理器自动生效。

- [ ] **Step 5: 提交**

```bash
git add apps/api/errors.py tests/test_errors.py
git commit -m "feat: unified error body for validation and unhandled exceptions"
```

---

### Task 7: 骨架验收与文档收口

**Files:**
- Modify: `README.md`
- Create: `tests/test_skeleton_acceptance.py`

**Interfaces:**
- Consumes: 全部前序 Task。
- Produces: 可演示的 M0 验收——`docker compose up` 起基础设施，应用可访问，鉴权全链路通，request_id 贯穿，统一错误体生效。

- [ ] **Step 1: 写端到端验收测试 `tests/test_skeleton_acceptance.py`**

```python
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
```

- [ ] **Step 2: 跑全量测试与 lint**

Run:
```bash
docker compose up -d
uv run pytest -v
uv run ruff check .
```
Expected: 全部 PASS，ruff 无错误。

- [ ] **Step 3: 手动冒烟（真实服务器）**

Run:
```bash
uv run uvicorn apps.api.main:create_app --factory --host 127.0.0.1 --port 8000
```
另开终端：
```powershell
# PowerShell（Windows）：curl 是 Invoke-WebRequest 的别名，需显式调用 curl.exe
curl.exe -i http://127.0.0.1:8000/api/v1/health
```
```bash
# Git Bash / Linux / macOS：
curl -i http://127.0.0.1:8000/api/v1/health
```
Expected: 200，响应头含 `X-Request-ID`，body `{"status":"ok"}`。验证后 Ctrl+C 停服务器。

- [ ] **Step 4: 更新 README 进度**

在 README `## 状态` 下替换为：
```markdown
## 状态
M0 骨架完成：Compose 基础设施、配置/日志/request_id、异步 DB+迁移、JWT 鉴权、统一错误体。
下一步：M1 模型网关（见 docs/superpowers/plans/ 后续计划）。
```

- [ ] **Step 5: 提交**

```bash
git add README.md tests/test_skeleton_acceptance.py
git commit -m "test: M0 skeleton acceptance and README progress"
```

---

## Self-Review

**1. Spec coverage（M0 范围）：**
- PRD M0「FastAPI 骨架、Docker Compose、PostgreSQL/pgvector/Redis、JWT、日志与 request_id」→ Task 1–7 覆盖；前端骨架按“后端优先”归 M7，PRD M0 交付物已同步修订，本计划不含前端。
- PRD 9.3 鉴权（access 2h/refresh 7d、密钥掩码、Fernet）→ Task 5 JWT TTL 覆盖；Fernet 凭证加密属 Plan 2 凭证接口，本计划仅建配置与日志过滤（Global Constraints 已注明）。
- PRD 9.1 统一错误体 → Task 3（AppError 基础处理器）+ Task 6（校验/未捕获处理器补齐）。
- PRD 8.2 全表 user_id → User 为根表，后续业务表带 user_id（Plan 2+）；本计划 User 无 user_id 自身（它是租户根），符合。
- PRD 11 NFR-5 结构化日志+request_id → Task 3。
- PRD 12.2 密钥不落日志 → Task 3 `_redact_secrets`；detect-secrets pre-commit/CI 属 Plan 9，本计划仅 .gitignore 覆盖 .env（Global Constraints 注明）。
- 设计文档地基（checkpointer 复用 PG、业务服务工具签名前瞻）→ PG 就绪（Task 2/4）；工具签名前瞻在 Plan 2 起落地，本计划不涉及。
- **缺口（有意延后，非遗漏）**：前端骨架、Fernet 凭证接口、detect-secrets hook、Idempotency-Key 落地、游标分页实现——均属后续计划，已在 Global Constraints/路线图标注。

**2. Placeholder scan：** 无 TBD/TODO；所有代码步骤含真实代码；每个 Task 自带红绿测试循环，无跨任务跳转（AppError 基础模块在 Task 3 落地，Task 5 鉴权与 Task 6 错误补齐各自独立）。

**3. Type consistency：** `create_app`、`get_settings`、`get_session`、`User`、`AppError(code,message,status_code,retryable)`、`register_error_handlers`、`request_id_var`、fixtures `client`/`db_session`/`test_engine` 在各 Task 间签名一致；TokenResponse/UserResponse 字段与测试断言一致。

**已知执行注意：** 无跨任务依赖阻塞。Task 1→7 严格线性：每个 Task 仅消费前序 Task 已提交的产物。Task 3 交付 AppError 基础处理器后，Task 5（鉴权）与 Task 6（错误补齐）可各自独立跑通红绿循环。所有 DB 相关测试（Task 4 起）需先 `docker compose up -d`。

## 执行适配记录（2026-11-17 实跑）

- 本机默认 Python 3.10 不满足 3.11+ 要求，改用已安装的 Python 3.14；uv 通过 `py -3.14 -m pip install uv` 安装，全部命令前缀为 `py -3.14 -m uv ...`。
- 宿主 5432 已被本地 PostgreSQL 占用，compose 将容器 5432 映射到宿主 5433；`.env` / `.env.example` / 连接串 / 测试 / 文档已同步。
- Docker Desktop 原有三个镜像源均失效，已替换为可用镜像源；此项属于本机 Docker 配置，与项目代码无关。
- Windows 下 asyncpg 在默认 `ProactorEventLoop` 上连接被重置，`tests/conftest.py` 与迁移 `env.py` 均设置 `WindowsSelectorEventLoopPolicy`；测试引擎使用 `NullPool`，避免 session 级引擎跨函数级事件循环复用连接。
- 依赖解析到较新版本（pytest-asyncio 1.5 / SQLAlchemy 2.1 / ruff 0.17），因此增加 `asyncio_default_fixture_loop_scope = "function"` 与 `ruff.lint.ignore = ["B008"]`，并把 `datetime.now(timezone.utc)` 改为 `datetime.now(UTC)`。
- 验收结果：`pytest` 14 passed，`ruff check .` 无错误，真实 uvicorn 冒烟返回 200 且响应头含 `X-Request-ID`。