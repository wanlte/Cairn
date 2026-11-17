# Cairn

多平台 AI 对话复盘与成长档案系统（个人开源项目）。

## 状态
M0 至 M8 完成：Compose 基础设施、配置/日志/request_id、异步 DB+迁移、JWT 鉴权、统一错误体；M1 模型网关含 Provider 薄适配、能力矩阵、降级链、限流熔断、密钥环境变量/加密凭证双模式与计量；M2 摄入管道含 Markdown/DeepSeek ZIP 采集、归一化、去重、预览与纠错；M3 抽取服务含版本化 prompt、单次调用四类碎片、知识点合并、失败记录与 SSE 进度；M4 复盘引擎含五段式报告、证据约束、UNVERIFIED 强制、行动项与逐条反馈；M5 画像引擎含五组维度、增量快照、证据引用、用户修正继承与画像 diff；M6 检索服务含 OpenAI 兼容 embedding、pgvector HNSW、中文 BM25、RRF 融合、Rerank、组合过滤与画像感知问答；M7 前端含 Vue 3 + Vite + TS 五页、SSE 进度、摄入纠错、逐条反馈、画像修正、问答来源与凭证/用量面板；M8 评测含抽取字段准确率、复盘一致率、Recall@5 API 与合成标签集，并补齐 MIT 许可证、架构/采集/评测说明。
注意：`eval/labels/` 为合成标签，仅验证评测管线；正式质量门槛仍需人工标注集验证。
M9 行动项闭环已补全：行动项状态、验证备注、跨报告列表、重开、复盘/画像 Markdown 导出与前端按钮。
下一步：进入连续四周自用，补充人工标注集后用真实 Provider 重跑评测。

## 快速开始
前置：Python 3.11+、uv、Docker Desktop、Git。
```bash
cp .env.example .env
uv sync
docker compose up -d
uv run pytest
```

> 当前 `docker-compose.yml` 将容器 5432 映射到宿主 5433（本机 5432 已被其他 PostgreSQL 占用）；若宿主 5432 空闲，可改回 `5432:5432` 并同步更新 `.env` 的 `DATABASE_URL`。
