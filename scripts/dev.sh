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

(cd backend && ../.venv/bin/uvicorn app.main:app --reload) &
api_pid=$!
npm run dev --prefix frontend -- --host 127.0.0.1 &
web_pid=$!

echo "API:       http://127.0.0.1:8000"
echo "Dashboard: http://127.0.0.1:5173"
wait -n "$api_pid" "$web_pid"
