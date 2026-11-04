#!/usr/bin/env bash
# Start API (:8000) and web dev server (:5173, proxies /api) together.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/services/api"
[ -f .env ] && set -a && . ./.env && set +a
.venv/bin/uvicorn app.main:app --reload --port 8000 &
API=$!
trap 'kill $API' EXIT
cd "$ROOT/apps/web" && npm run dev
