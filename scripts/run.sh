#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p data

# One-time migration: drop legacy per-session checkpoint DB. The backend
# is now stateless; persistence lives entirely in the browser's
# localStorage. Safe to leave in — it only acts when the file exists.
rm -f data/checkpoints.db

# 首启：自动入索引（OFFLINE=1 下也允许，因为 PDF 加载不依赖 embedding）
if [ ! -d data/chroma ]; then
  echo "[run] first run, building index..."
  uv run python -m ingest.indexer
fi

# 前端产物检查：web/dist 是 Vue SPA 的构建输出（已随仓库提交）。
# 缺失时（如手工清理过）提示如何重建，而不是启动后 404。
if [ ! -f web/dist/index.html ]; then
  echo "[run] ERROR: web/dist/index.html 不存在（前端产物缺失）。"
  echo "      请执行: cd frontend && pnpm install && pnpm build"
  exit 1
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
echo "[run] starting uvicorn on ${HOST}:${PORT}"
exec uv run uvicorn app.main:app --host "${HOST}" --port "${PORT}" --reload
