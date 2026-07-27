#!/usr/bin/env bash
#
# scripts/run.sh — start the AI Counselor backend with auto-index on first run.
#
# Usage:
#   bash scripts/run.sh
#
# Override host / port (defaults shown):
#   HOST=127.0.0.1 PORT=8080 bash scripts/run.sh
#
# Other env vars respected by the backend (see CLAUDE.md):
#   LLAMACPP_BASE_URL, MODEL_NAME, EMBED_MODEL, DOCUMENTS_DIR, DATA_DIR,
#   OFFLINE, CHUNK_SIZE, CHUNK_OVERLAP, RETRIEVE_K, COUNSELOR_ALLOWED_ORIGIN.

set -euo pipefail
cd "$(dirname "$0")/.."

# Disable chromadb's posthog telemetry (see CLAUDE.md "known pitfalls").
# chromadb 0.6.x calls posthog.capture() with 3 positional args; posthog
# 7.x only accepts 1 positional arg → every event fails with
# `capture() takes 1 positional argument but 3 were given`.
export ANONYMIZED_TELEMETRY="${ANONYMIZED_TELEMETRY:-False}"

mkdir -p data

# One-time migration: drop legacy per-session checkpoint DB. The backend
# is now stateless; persistence lives entirely in the browser's
# localStorage. Safe to leave in — it only acts when the file exists.
rm -f data/checkpoints.db

# 首启：自动入索引（OFFLINE=1 下也允许，因为 PDF 加载不依赖 embedding）
if [ ! -d data/chroma ]; then
  echo "[run] first run, building index..."
  uv run python -m ingest
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

# Validate PORT (1-65535, digits only) so we fail fast with a clear message
# instead of uvicorn's bind-time error.
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  echo "[run] ERROR: PORT='$PORT' is not a valid port (expected 1-65535)" >&2
  exit 1
fi
if [ -z "$HOST" ]; then
  echo "[run] ERROR: HOST is empty" >&2
  exit 1
fi

echo "[run] starting uvicorn on ${HOST}:${PORT}"
exec uv run uvicorn app.main:app --host "${HOST}" --port "${PORT}" --reload
