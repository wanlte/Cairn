# Cairn API 生产镜像（仓库根目录构建）
# 本地开发不要用本文件，按 README 的 uv + docker compose 方式启动
# Python 版本与本地开发环境保持一致（uv.lock 在该版本下验证过）
FROM python:3.14-slim

# 只影响安装 uv 本身；项目依赖按 uv.lock 中锁定的下载地址获取，不走这个源
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    UV_LINK_MODE=copy

# 时区数据基础镜像已自带，健康检查用 Python 标准库，因此不安装任何 apt 包：
# 国内访问 Debian 软件源经常 502/超时，构建不应依赖它
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" uv

WORKDIR /app

# 先装依赖：代码改动不会触发依赖重装，利用构建缓存
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 业务代码。prompts/ 与 eval/labels/ 按仓库根相对路径加载（parents[3]），目录结构不可变
COPY alembic.ini ./
COPY apps/__init__.py ./apps/__init__.py
COPY apps/api ./apps/api
COPY prompts ./prompts
# 只带合成标签集；eval/labels/human 是真实对话标注，不进镜像
COPY eval/labels/*.jsonl ./eval/labels/

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# 生产用单进程 + asyncio（2 核足够；需要横向扩容时改 --workers 并配合反向代理）
CMD ["python", "-m", "uvicorn", "apps.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
