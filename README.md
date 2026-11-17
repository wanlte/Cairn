# Cairn

多平台 AI 对话复盘与成长档案系统（个人开源项目）。

## 状态
M0 至 M8 完成：Compose 基础设施、配置/日志/request_id、异步 DB+迁移、JWT 鉴权、统一错误体；M1 模型网关含 Provider 薄适配、能力矩阵、降级链、限流熔断、密钥环境变量/加密凭证双模式与计量；M2 摄入管道含 Markdown/DeepSeek ZIP 采集、归一化、去重、预览与纠错；M3 抽取服务含版本化 prompt、单次调用四类碎片、知识点合并、失败记录与 SSE 进度；M4 复盘引擎含五段式报告、证据约束、UNVERIFIED 强制、行动项与逐条反馈；M5 画像引擎含五组维度、增量快照、证据引用、用户修正继承与画像 diff；M6 检索服务含 OpenAI 兼容 embedding、pgvector HNSW、中文 BM25、RRF 融合、Rerank、组合过滤与画像感知问答；M7 前端含 Vue 3 + Vite + TS 五页、SSE 进度、摄入纠错、逐条反馈、画像修正、问答来源与凭证/用量面板；M8 评测含抽取字段准确率、复盘一致率、Recall@5 API 与合成标签集，并补齐 MIT 许可证、架构/采集/评测说明。
注意：`eval/labels/` 为合成标签，仅验证评测管线；正式质量门槛仍需人工标注集验证。
M9 行动项闭环已补全：行动项状态、验证备注、跨报告列表、重开、复盘/画像 Markdown 导出与前端按钮。
M10 对话式工作区已上线：前端收敛为单一对话首页（顶部仅「对话 / 画像」切换），支持多文件拖拽上传、自动推荐复盘方向、模型快速通道与临时密钥；后端引入 LangGraph + LangChain 多 Agent 协作（整理师 / 复盘师 / 画像师 / 问答教练 / 审核员），LangGraph 仅作编排器，所有模型调用统一经自定义适配器回到 `ModelGateway.complete()`，保留能力矩阵、降级链、限流熔断与计量。临时密钥单次使用、不落库、不回显。
下一步：进入连续四周自用，补充人工标注集后用真实 Provider 重跑评测。

## 快速开始
前置：Python 3.11+、uv、Docker Desktop、Node.js 20+、Git。

首次准备：

```powershell
cd f:/work/Cairn
copy .env.example .env
uv sync
docker compose up -d
.venv/Scripts/python.exe -m alembic upgrade head
```

> Windows 上 `uv run pytest` / `uv run uvicorn` 可能触发 `uv trampoline failed to canonicalize script path`。这是 uv 的 console-script launcher 问题，不影响项目；请统一用上面的 `.venv/Scripts/python.exe -m ...` 方式。macOS/Linux 把路径换成 `.venv/bin/python`。

启动后端（终端 1）：

```powershell
cd f:/work/Cairn
.venv/Scripts/python.exe -m uvicorn apps.api.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

启动前端（终端 2）：

```powershell
cd f:/work/Cairn/apps/web
npm install
npm run dev
```

打开：

- 前端：http://127.0.0.1:5173
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/v1/health

真实模型调用前，在 `.env` 里配置至少一个 `*_API_KEY`，或在对话首页右上角的模型快速通道里选择已保存凭证、临时密钥；不要提交 `.env`。

使用方式：打开首页后在对话框里说明需求（如「帮我复盘这周」），可拖拽或点击附带多个 Markdown / TXT / ZIP 对话文件；系统会自动推荐复盘方向（可改），由整理师、复盘师、画像师、问答教练、审核员依次协作，页面上以友好气泡展示进度，结果需要你确认后才会正式保存。顶部切换到「画像」可查看、修正、比较与导出成长画像。

测试：

```powershell
cd f:/work/Cairn
.venv/Scripts/python.exe -m pytest
```

停止服务：分别按 `Ctrl+C`；停止基础设施：`docker compose down`。

> 当前 `docker-compose.yml` 将容器 5432 映射到宿主 5433（本机 5432 已被其他 PostgreSQL 占用）；若宿主 5432 空闲，可改回 `5432:5432` 并同步更新 `.env` 的 `DATABASE_URL`。
