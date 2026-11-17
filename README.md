# Cairn

多平台 AI 对话复盘与成长档案系统（个人开源项目）。

## 状态
M0 骨架、M1 模型网关与 M2 摄入管道完成：Compose 基础设施、配置/日志/request_id、异步 DB+迁移、JWT 鉴权、统一错误体；M1 新增 OpenAI 兼容 Provider 薄适配、能力矩阵与探测、降级链、令牌桶+信号量+熔断、密钥环境变量/加密凭证双模式、调用计量与用量查询；M2 新增 Markdown/DeepSeek ZIP 采集器、归一化、去重、摄入预览、纠错确认与不可变原始层，并用 `samples/` 做快照测试。
下一步：M3 抽取服务。

## 快速开始
前置：Python 3.11+、uv、Docker Desktop、Git。
```bash
cp .env.example .env
uv sync
docker compose up -d
uv run pytest
```

> 当前 `docker-compose.yml` 将容器 5432 映射到宿主 5433（本机 5432 已被其他 PostgreSQL 占用）；若宿主 5432 空闲，可改回 `5432:5432` 并同步更新 `.env` 的 `DATABASE_URL`。
