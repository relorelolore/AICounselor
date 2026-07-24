#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p data

# 首启：自动入索引（OFFLINE=1 下也允许，因为 PDF 加载不依赖 embedding）
if [ ! -d data/chroma ]; then
  echo "[run] first run, building index..."
  uv run python -m ingest.indexer
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
echo "[run] starting uvicorn on ${HOST}:${PORT}"
exec uv run uvicorn app.main:app --host "${HOST}" --port "${PORT}" --reload
