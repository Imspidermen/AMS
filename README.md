# SSAMS — Smart Student Attendance Management System

SSAMS is a locally operated attendance application with a FastAPI service, PostgreSQL production support, SQLite local/test support, and a responsive React/TypeScript web client. Students request attendance for an eligible session; the server independently validates enrollment, schedule, geofence, temporal liveness, and a 1:1 match against that student's encrypted face template before writing an attendance record.

> **Biometric and location caution:** this software is not spoof-proof, a legal-compliance determination, or a substitute for accessible attendance alternatives and human review. A geolocation reading can be inaccurate or manipulated. Blink/head-turn liveness prompts are basic active signals, not certified anti-spoofing. The pinned SFace model's training-data provenance is not established here. Obtain institutional privacy, accessibility, security, and legal approval before enrolling anyone.

## What is included

- Role-gated Admin, Teacher, and Student workspaces; server-side authorization, opaque HttpOnly sessions, session-bound CSRF checks, Argon2id passwords, account activation, and password-reset links.
- Academic departments, years, semesters, courses, sections, student enrollment, teaching assignments, locations/geofences, class schedules, attendance registers, correction review, audit trail, CSV/print reports, and in-app notifications.
- Local CPU inference using OpenCV YuNet/SFace for face detection and 1:1 face comparison, plus a separate MediaPipe Face Mesh temporal blink/head-turn challenge. Model files are installed explicitly and SHA-256 checked; there is no runtime model download.
- Server-side geofence and schedule checks; idempotent attendance writes; UTC timestamps displayed in the configured campus IANA timezone.
- Linux and native Windows setup/run scripts, Alembic migrations, operational backup/restore tools, privacy/model notices, and automated tests.

See [setup](docs/SETUP.md), [operations](docs/OPERATIONS.md), [privacy and security](docs/PRIVACY_AND_SECURITY.md), [troubleshooting](docs/TROUBLESHOOTING.md), and the [model card](models/MODEL_CARD.md) before deployment.

## Quick start (Linux)

From the repository root:

```bash
./scripts/setup_linux.sh
cd backend
.venv/bin/python -m app.cli generate-secrets
cd ..
# Edit .env: set the generated secrets, campus timezone, and other local settings.
./scripts/run_linux.sh
```

Open `http://localhost:5173` for local development. In a second terminal, create the first administrator:

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

Create the first administrator in a separate PowerShell window:

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m app.cli create-admin
```

Native Windows commands are provided but have **not** been exercised in this Linux environment. See [SETUP.md](docs/SETUP.md) for TLS, PostgreSQL, phone access, and production deployment steps.

## Verify changes

```bash
# Python backend, from backend/
.venv/bin/python -m pytest -q
.venv/bin/python -m alembic check

# TypeScript frontend, from frontend/
npm test
npm run build
```

Model checks require the explicitly installed local weights:

```bash
cd backend
.venv/bin/python -m app.cli model-check
```

See [BUILD_STATUS.md](docs/BUILD_STATUS.md) for tested results and remaining validation limits. Never use `data/ssams.db` as a disposable test database; pytest is configured to use the separate ignored `data/ssams-tests.sqlite3` file.
