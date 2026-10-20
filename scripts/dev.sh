#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ ! -x .venv/bin/python ]]; then
  echo "Python environment not found. Run: make setup" >&2
  exit 1
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "Frontend dependencies not found. Run: make setup" >&2
  exit 1
fi

if [[ ! -f backend/.env ]]; then
  echo "backend/.env is missing. Copy backend/.env.example and add the required values." >&2
  exit 1
fi

api_pid=""
web_pid=""
cleanup() {
  [[ -n "$api_pid" ]] && kill "$api_pid" 2>/dev/null || true
  [[ -n "$web_pid" ]] && kill "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

backend_port="${BACKEND_PORT:-8000}"
if [[ "$backend_port" != "8000" && "$backend_port" != "8001" && "$backend_port" != "8002" ]]; then
  echo "BACKEND_PORT must be 8000, 8001, or 8002." >&2
  exit 1
fi
frontend_port="${FRONTEND_PORT:-5173}"
if [[ "$frontend_port" != "5173" && "$frontend_port" != "5174" ]]; then
  echo "FRONTEND_PORT must be 5173 or 5174." >&2
  exit 1
fi
export PUBLIC_APP_URL="http://127.0.0.1:${frontend_port}"

(cd backend && ../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port "$backend_port") &
api_pid=$!
npm run dev --prefix frontend -- --host 127.0.0.1 --port "$frontend_port" --strictPort &
web_pid=$!

echo "API:       http://127.0.0.1:$backend_port"
echo "Dashboard: $PUBLIC_APP_URL"
wait -n "$api_pid" "$web_pid"
