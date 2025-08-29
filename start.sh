#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1
export PORT="${PORT:-7860}"
export CHAINLIT_APP_ROOT="${CHAINLIT_APP_ROOT:-/tmp}"

echo "[startup] 🚀 Starting Chainlit app"
echo "[startup] PORT=$PORT  AWS_REGION=${AWS_DEFAULT_REGION:-unset}"

exec chainlit run app/main.py --host 0.0.0.0 --port "$PORT"