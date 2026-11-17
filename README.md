# Cairn

多平台 AI 对话复盘与成长档案系统（个人开源项目）。

## 状态
M0 骨架完成：Compose 基础设施、配置/日志/request_id、异步 DB+迁移、JWT 鉴权、统一错误体。
下一步：M1 模型网关（见 `docs/superpowers/plans/` 后续计划）。

## 快速开始
前置：Python 3.11+、uv、Docker Desktop、Git。
```bash
cp .env.example .env
uv sync
docker compose up -d
uv run pytest
```

> 当前 `docker-compose.yml` 将容器 5432 映射到宿主 5433（本机 5432 已被其他 PostgreSQL 占用）；若宿主 5432 空闲，可改回 `5432:5432` 并同步更新 `.env` 的 `DATABASE_URL`。
