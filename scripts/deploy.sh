#!/usr/bin/env bash
# Cairn 生产发布脚本：构建 -> 启动 -> 健康检查 -> 数据库迁移
# 在服务器上于仓库根目录执行：bash scripts/deploy.sh
# 首次使用前先按 docs/DEPLOYMENT.md 创建 .env.production
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE")

if [[ ! -f "$ENV_FILE" ]]; then
  echo "缺少 $ENV_FILE：请先复制 .env.production.example 并逐项填写（见 docs/DEPLOYMENT.md）" >&2
  exit 1
fi

echo "==> 构建镜像（逐个构建：小内存机器并发构建容易 OOM）"
"${COMPOSE[@]}" build api
"${COMPOSE[@]}" build web

echo "==> 启动服务"
"${COMPOSE[@]}" up -d

echo "==> 等待 API 通过健康检查"
HC="import http.client; c = http.client.HTTPConnection('127.0.0.1', 8000, timeout=3); c.request('GET', '/api/v1/health'); raise SystemExit(0 if c.getresponse().status == 200 else 1)"
ok=0
for _ in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T api python -c "$HC" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done
if [[ $ok != 1 ]]; then
  echo "API 健康检查未通过，查看日志：${COMPOSE[*]} logs api" >&2
  exit 1
fi

echo "==> 执行数据库迁移（alembic upgrade head）"
"${COMPOSE[@]}" exec -T api python -m alembic upgrade head

echo "==> 发布完成"
"${COMPOSE[@]}" ps
echo "前端: http://<服务器IP>/   API 文档: /docs   健康检查: /api/v1/health"
