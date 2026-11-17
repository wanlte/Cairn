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
