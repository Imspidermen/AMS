#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.11 was not found. Install Python 3.11 (and its venv/Dev headers) or set PYTHON_BIN." >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "Node.js and npm were not found. Install a supported Node.js release first." >&2
  exit 1
fi
if ! node -e 'const [major, minor] = process.versions.node.split(".").map(Number); const ok = (major === 22 && minor >= 12) || major === 24 || major >= 26; if (!ok) { console.error(`Unsupported Node.js ${process.versions.node}; use 22.12+, 24.x, or 26+.`); process.exit(1); }'; then
  exit 1
fi

"$PYTHON_BIN" -m venv "$ROOT/backend/.venv"
"$ROOT/backend/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/backend/.venv/bin/python" -m pip install -r "$ROOT/backend/requirements.txt"
npm --prefix "$ROOT/frontend" ci
mkdir -p "$ROOT/data"
if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created .env from the safe template. Replace both secret placeholders before running SSAMS."
else
  echo "Existing .env preserved. Review its database, secret, timezone and cookie settings."
fi
cat <<'EOF'
Dependencies are installed. Before starting the app:
  1. Edit .env and set unique SESSION_SECRET and BIOMETRIC_ENCRYPTION_KEY values.
  2. Use `cd backend && .venv/bin/python -m app.cli generate-secrets` to generate candidates.
  3. Run `scripts/run_linux.sh` from the repository root for the unified single-port app
     (http://localhost:8000), or `scripts/dev_linux.sh` for the Vite development workflow
     (http://localhost:5173).
The application timezone defaults to Asia/Kolkata (IST, UTC+05:30); no host timezone change is needed.
EOF
