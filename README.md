# SSAMS — Smart Student Attendance Management System

SSAMS is a locally operated attendance application with a FastAPI service, PostgreSQL production support, SQLite local/test support, and a responsive React/TypeScript web client. Students request attendance for an eligible session; the server independently validates enrollment, schedule, geofence, temporal liveness, and a 1:1 match against that student's encrypted face template before writing an attendance record.

> **Biometric and location caution:** this software is not spoof-proof, a legal-compliance determination, or a substitute for accessible attendance alternatives and human review. A geolocation reading can be inaccurate or manipulated. Blink/head-turn liveness prompts are basic active signals, not certified anti-spoofing. The pinned SFace model's training-data provenance is not established here. Obtain institutional privacy, accessibility, security, and legal approval before enrolling anyone.

## What is included

- Role-gated Admin, Teacher, and Student workspaces; server-side authorization, opaque HttpOnly sessions, session-bound CSRF checks, Argon2id passwords, account activation, and password-reset links.
- Academic departments, years, semesters, courses, sections, student enrollment, teaching assignments, locations/geofences, class schedules, attendance registers, correction review, audit trail, CSV/print reports, and in-app notifications.
- Local CPU inference using OpenCV YuNet/SFace for face detection and 1:1 face comparison, plus a separate MediaPipe Face Mesh temporal blink/head-turn challenge. Model files are installed explicitly and SHA-256 checked; there is no runtime model download.
- Server-side geofence and schedule checks; idempotent attendance writes.
- **India Standard Time by default.** Timestamps are stored as UTC instants and every business rule, API response, report and screen uses the configured campus timezone — `Asia/Kolkata` (IST, UTC+05:30) unless changed.
- **One public port.** A single FastAPI process serves the built React application at `/` and the backend under `/api`, so one tunnel (ngrok/Cloudflare) exposes the whole application.
- Linux and native Windows setup/run scripts, Alembic migrations, operational backup/restore tools, privacy/model notices, and automated tests.

See [setup](docs/SETUP.md), [operations](docs/OPERATIONS.md), [privacy and security](docs/PRIVACY_AND_SECURITY.md), [troubleshooting](docs/TROUBLESHOOTING.md), and the [model card](models/MODEL_CARD.md) before deployment.

## Running the Application

### Timezone

Application timezone: **`Asia/Kolkata`** (IST / UTC+05:30), configured with `CAMPUS_TIMEZONE` in the root `.env`.

- Instants are stored as UTC so the recorded moment is exact and the database stays portable.
- Attendance days, class windows, lateness, "today", reports, exports, API timestamps and log lines are computed in IST, not in the host operating-system timezone.
- API timestamps are timezone-aware ISO 8601, for example `"marked_at": "2026-10-07T20:30:00+05:30"` with a companion `"marked_on_ist": "2026-10-07"`.
- Attendance date filters (`?start=`/`?end=`, `?from_date=`/`?to_date=`) interpret a bare date as an IST calendar day, so a record marked at 23:59 IST belongs to that Indian day even if the server clock is still on the previous UTC day.
- The Windows/PC timezone does not have to be changed; the application never depends on it.
- Verify at any time: `cd backend` then `python -m app.cli timezone-check` (or `http://localhost:8000/api/health`).

### Unified Port

Frontend and backend are available through **one** public port:

```text
http://localhost:8000
```

```text
http://localhost:8000/        → React application (SPA deep links fall back to index.html)
http://localhost:8000/assets/ → hashed frontend assets
http://localhost:8000/api/v1  → FastAPI routes
http://localhost:8000/docs    → API documentation (redirects to /api/v1/docs)
http://localhost:8000/api/health → liveness JSON with the active timezone
```

The port is defined once, as `APP_PORT` in the root `.env`, and the server binds `APP_HOST`
(`0.0.0.0` by default so a tunnel or a phone on the LAN can reach it).

### Development mode

Hot-reload development is preserved (Vite dev server + API in two processes; Vite proxies `/api` to the backend so the browser still uses a single origin):

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File .\scripts\dev_windows.ps1     # Vite http://localhost:5173 + API :8000
```

```bash
# Linux/macOS
./scripts/dev_linux.sh
```

### Unified/tunnel mode

```powershell
# Windows — builds the frontend if needed, migrates, then serves everything on APP_PORT
powershell -ExecutionPolicy Bypass -File .\scripts\run_windows.ps1
```

```bash
# Linux/macOS
./scripts/run_linux.sh
```

### Ngrok

```powershell
ngrok http 8000
```

Open the generated HTTPS URL (`https://xxxxx.ngrok-free.app/`) — the application, the SPA routes
(`/login`, `/admin`, `/student`, …), `/api/*` and `/docs` are all served from that single URL.
Only one tunnel is required; never expose `5173` separately. A secure HTTPS origin is also what
lets a phone use the camera and geolocation.

### Environment variables (root `.env`, see `.env.example`)

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development` or `production` (production forces Secure cookies + HSTS) |
| `APP_HOST`, `APP_PORT` | The single public bind address/port (default `0.0.0.0:8000`) |
| `CAMPUS_TIMEZONE` | Business/application timezone (default `Asia/Kolkata`) |
| `FRONTEND_DIST` | Built frontend directory served at `/` (default `frontend/dist`) |
| `DATABASE_URL` | `sqlite:///../data/ssams.db` locally, PostgreSQL in production |
| `SESSION_SECRET`, `BIOMETRIC_ENCRYPTION_KEY` | Required secrets; generate with `app.cli generate-secrets` |
| `COOKIE_SECURE` | `false` for localhost HTTP, `true` for HTTPS (tunnel/TLS proxy) |
| `MODEL_DIR` | Directory with the pinned local face models |
| `CORS_ORIGINS` | Empty by default (same origin); only set for a deliberate cross-origin deployment |

## Quick start (Linux)

From the repository root:

```bash
./scripts/setup_linux.sh
cd backend
.venv/bin/python -m app.cli generate-secrets
cd ..
# Edit .env: set the generated secrets (timezone and port already default to IST/8000).
./scripts/run_linux.sh
```

Open `http://localhost:8000`. In a second terminal, create the first administrator:

```bash
cd backend
.venv/bin/python -m app.cli create-admin
```

The initial app remains useful for academic setup and API testing while face models are absent, but attendance enrollment/verification will remain disabled. Review the model card, then explicitly install and verify model weights as described in [SETUP.md](docs/SETUP.md).

## Quick start (native Windows PowerShell)

From the repository root, in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
Set-Location .\backend
.\.venv\Scripts\python.exe -m app.cli generate-secrets
Set-Location ..
# Edit .env and replace both secret placeholders.
powershell -ExecutionPolicy Bypass -File .\scripts\run_windows.ps1
```

Open `http://localhost:8000`. Create the first administrator in a separate PowerShell window:

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m app.cli create-admin
```

Native Windows commands are provided but have **not** been exercised in this Linux environment. See [SETUP.md](docs/SETUP.md) for TLS, PostgreSQL, phone access, and production deployment steps.

## Verify changes

```bash
# Python backend, from backend/
.venv/bin/python -m pytest -q          # 41 tests, including IST boundary and unified-port coverage
.venv/bin/python -m alembic check      # no schema drift

# TypeScript frontend, from frontend/
npm test                               # 14 tests
npm run build                          # tsc -b + vite build (outputs frontend/dist)

# Single-port smoke test (after the build), from backend/
.venv/bin/python -m app.cli serve      # / , /docs , /api/health , /api/v1/health/ready
.venv/bin/python -m app.cli timezone-check
```

Model checks require the explicitly installed local weights:

```bash
cd backend
.venv/bin/python -m app.cli model-check
```

See [BUILD_STATUS.md](docs/BUILD_STATUS.md) for tested results and remaining validation limits. Never use `data/ssams.db` as a disposable test database; pytest is configured to use the separate ignored `data/ssams-tests.sqlite3` file.
