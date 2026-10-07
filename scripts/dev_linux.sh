#!/usr/bin/env bash
# Development mode: FastAPI on APP_PORT plus the Vite dev server on port 5173.
# Vite proxies /api to the backend, so the browser only talks to http://localhost:5173.
# Use scripts/run_linux.sh for the unified single-port application (and for tunnels).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "$ROOT/.env" ]]; then
  echo "Missing $ROOT/.env. Run scripts/setup_linux.sh, then configure the secrets." >&2
  exit 1
fi
if grep -Eq '^SESSION_SECRET=(replace-|$)|^BIOMETRIC_ENCRYPTION_KEY=(replace-|$)' "$ROOT/.env"; then
  echo "Replace the secret placeholders in .env before starting SSAMS." >&2
  exit 1
fi
if [[ ! -x "$ROOT/backend/.venv/bin/python" ]]; then
  echo "Backend environment is missing. Run scripts/setup_linux.sh first." >&2
  exit 1
fi
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "Frontend dependencies are missing. Run scripts/setup_linux.sh first." >&2
  exit 1
fi

backend_pid=''
cleanup() {
  if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" 2>/dev/null; then
    kill "$backend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

cd "$ROOT/backend"
.venv/bin/python -m app.cli migrate
.venv/bin/python -m app.cli serve &
backend_pid=$!
printf 'API starting on http://0.0.0.0:8000; Vite proxies /api to this backend.\n'
cd "$ROOT/frontend"
npm run dev -- --host 0.0.0.0 --port 5173
