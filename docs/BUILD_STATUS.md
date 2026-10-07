# SSAMS build and validation status

**Status as of 2026-10-07:** implementation and Linux-hosted automated validation are complete for the features listed below, including the India Standard Time (IST) application timezone and the unified single-port architecture. This is not a production certification. Native Windows, PostgreSQL, model inference, phone sensors, tunnels and institutional/legal review remain unverified.

## Change validation — 2026-10-07 (IST timezone + single port)

Commands run in this environment (Linux x86_64, Python 3.11.2, Node 22.22.3, npm 10.9.8,
PostgreSQL/PowerShell/ngrok absent):

```bash
# backend/ (venv installed from requirements.lock)
.venv/bin/python -m pytest -q
# Result: 42 passed, 1 upstream Starlette/AnyIO deprecation warning.
#         26 pre-existing tests + 9 new IST tests (tests/test_timezone.py)
#         + 7 new unified-port tests (tests/test_unified_port.py).

.venv/bin/python -m pytest tests/test_timezone.py -q
# Result: 9 passed. Covers: Asia/Kolkata + +05:30 defaults; UTC→IST ISO output
#         (15:00Z → 2026-10-07T20:30:00+05:30); IST-midnight day boundaries
#         (18:30Z ↔ 18:30Z); 23:59/00:01 IST calendar-date rollover; IST timestamps
#         and marked_on_ist in attendance/session APIs; ?start/?end date filters
#         selecting 23:30 IST but not 00:30 IST; teacher ?from_date/?to_date
#         filters; IST CSV/print exports; health endpoints reporting the zone.

.venv/bin/python -m alembic check
# Result: No new upgrade operations detected (no schema change was required).

.venv/bin/python -m app.cli migrate            # data/ssams.db (ignored local DB)
.venv/bin/python -m app.cli timezone-check
# Result: Asia/Kolkata (UTC+05:30); Indian calendar date 2026-10-07;
#         IST day window 2026-10-07T00:00+05:30 .. 2026-10-08T00:00+05:30;
#         stored boundaries 2026-10-06T18:30Z .. 2026-10-07T18:30Z (UTC, exclusive).

# frontend/
npm test
# Result: 14 passed across 3 files (11 pre-existing + 3 new IST default tests).
npx tsc -b && npm run build
# Result: TypeScript check and Vite production build succeeded (frontend/dist).

# unified single-port server (backend/, using the local .env)
.venv/bin/python -m app.cli serve
```

Live HTTP checks against `http://127.0.0.1:8000` while that server was running:

```text
GET  /                       200 text/html (built React shell, id="root")
GET  /login                  200 text/html (SPA deep-link fallback)
HEAD /                       200
GET  /assets/<hashed>.js     200, Cache-Control: public, max-age=31536000, immutable
GET  /api/health             200 {"status":"ok","campus_timezone":"Asia/Kolkata","campus_utc_offset":"+05:30","server_time_local":"2026-10-07T20:19:26+05:30"}
GET  /api/v1/health/live     200 alive + campus timezone/offset/server time
GET  /api/v1/health/ready    200 ready, database connected, campus_timezone Asia/Kolkata
GET  /docs                   307 → /api/v1/docs, then 200 Swagger UI
GET  /api/v1/does-not-exist  404 application/json {"detail":"API route not found","request_id":…}
POST /api/v1/auth/login      200 (session + CSRF cookies set); GET /api/v1/auth/me 200
GET  /api/v1/admin/attendance  "marked_at":"2026-10-07T20:30:00+05:30","marked_on_ist":"2026-10-07"
GET  /api/v1/admin/reports/attendance.csv  header marked_on_ist,marked_at_ist …
GET  /api/v1/admin/settings  campus_timezone Asia/Kolkata, campus_utc_offset +05:30
POST /api/v1/auth/logout without CSRF header  403 (CSRF enforcement preserved)
```

A late security-header adjustment follows the same rule: `X-Frame-Options: DENY` is now sent only
when `APP_ENV=production` (see `backend/app/main.py`), so the sandbox/preview iframe can display the
app during local development while production deployments stay non-embeddable.

Vite development mode was also exercised: `npm run dev -- --host 0.0.0.0 --port 5173` served the
SPA and proxied `/api/health`, `/api/v1/health/live` and a login POST to the backend on port 8000
(proxy target follows `APP_PORT` from the root `.env`), confirming the two-process workflow still
works with one browser origin.

**Not tested for these changes:** `ngrok`/Cloudflare Tunnel (no tunnel client installed), native
Windows/PowerShell execution, PostgreSQL (not installed), real camera/geolocation attendance,
face-model inference (weights unavailable), and Playwright E2E. Cookie behaviour through a real
HTTPS tunnel is therefore unverified; `COOKIE_SECURE=true` is documented for that case.

## Repository and environment

- Built in `/home/user/AMS` on branch `arena/05b234d0-ams` from an initially empty application repository (the starting repository contained the MIT license only).
- Validation environment: Linux x86_64, Python 3.11, Node.js 22.22.3, npm 10.9.2 (10.9.8 in the 2026-10-07 run). PostgreSQL client/server tools, PowerShell and ngrok are not installed.
- Backend tests use the isolated, ignored SQLite database `data/ssams-tests.sqlite3`. `data/ssams.db` is the local development database and is not used as a disposable test target.
- Production database support is implemented for PostgreSQL, but no PostgreSQL installation was available here.

## Implemented scope

- FastAPI/SQLAlchemy backend, Alembic migrations, SQLite local/test and PostgreSQL deployment configuration.
- Admin, Teacher, and Student authorization and workflows; password hashing, opaque server-managed sessions, CSRF protections, account activation/reset, audited corrections, academic setup, schedules, enrollment, locations, attendance, notifications, CSV/print reporting, and campus-timezone handling.
- Server-side schedule, enrollment, geofence, challenge, template and face-score checks; transactional/idempotent attendance writes; encrypted face embeddings; UTC instants stored with IST (Asia/Kolkata) business logic, API, export and display time.
- Unified single-port serving: FastAPI serves the built React app at `/` (SPA fallback) and the API under `/api`, with short `/docs` aliases, immutable asset caching and a JSON 404 for unknown API paths.
- CPU-local YuNet/SFace face detection and 1:1 comparison are implemented separately from temporal MediaPipe blink/head-turn checks. Readiness validates model hashes and the Fernet storage key. Models are never downloaded at startup; attendance is fail-closed when required checks are unavailable.
- Responsive React/TypeScript frontend; Linux and native Windows setup/run scripts; backup/restore tools; deployment templates; privacy, operations, troubleshooting, setup and model-license documentation.

## Automated validation performed

Commands run from the indicated directories:

```bash
# backend/
.venv/bin/python -m pytest -q
# Result: 26 passed; one upstream Starlette/AnyIO BlockingPortal deprecation warning.

.venv/bin/python -m alembic check
# Result: No new upgrade operations detected (SQLite development configuration).

# frontend/
npm test
# Result: 11 passed across 3 files. Vitest reports an informational worker/isolation performance hint.

npm run build
# Result: TypeScript check and Vite production build succeeded; largest generated JS chunk was ~400 kB (not gzip) and no oversized-chunk warning was emitted.

npm audit
# Result after updating vulnerable tool/router packages: 0 vulnerabilities.

# repository root
bash -n scripts/setup_linux.sh scripts/run_linux.sh
python3 -m compileall -q backend/app backend/tests scripts
git diff --check
# Result: all passed.
```

The backend tests include authorization, geofence rejection, challenge ownership/liveness timing, reports, encrypted-template handling, wrong model digest/key checks, and SQLite backup/restore safety. Tests do not establish biometric accuracy or sensor integrity. The frontend tests cover route authorization and shared API/admin utilities, not a full browser-device attendance session.

## Not tested / deployment blockers

- **Models:** pinned weights are not present in the repository or current workspace. Earlier download attempts failed with TLS/SSL EOF errors. `model-check`, real YuNet/SFace inference, enrollment quality, and CPU performance were not validated. Read `models/MODEL_CARD.md`; review upstream notices and obtain local legal/privacy approval before installation or enrollment.
- **Windows:** PowerShell setup/run scripts are provided but were not executed because PowerShell/native Windows was unavailable.
- **PostgreSQL:** migrations, PostgreSQL backup/restore, TLS, and production connection settings were not exercised. PostgreSQL and `pg_dump`/`pg_restore` binaries are not installed.
- **Hardware/browser:** no phone camera or location device was tested. Camera/geolocation require HTTPS on remote devices; indoor GPS and browser readings are not trusted identity evidence.
- **Production deployment:** Nginx/systemd/IIS templates, TLS certificates, access controls, backup retention, institutional policy, accessibility accommodations and operational runbooks require local review and rehearsal.
- **E2E:** Playwright browser tests were not run; only `npm test` unit/component tests and the production build were run.
- Starlette emits an upstream AnyIO deprecation warning during backend tests. Vitest's jsdom environment-sharing message is informational and does not fail tests.

## Required setup before real use

1. Install supported dependencies: Python 3.11–3.12 and Node.js 22.12+, 24.x, or 26+.
2. Run the platform setup script, copy `.env.example` if needed, and replace both secret placeholders. Generate candidates with `python -m app.cli generate-secrets`; keep `BIOMETRIC_ENCRYPTION_KEY` separately backed up. Do not change it without a template migration/reenrollment plan.
3. Set the correct `DATABASE_URL`, `CAMPUS_TIMEZONE`, secure cookies, allowed origins, and institutional HTTPS/reverse proxy. Review and apply Alembic migrations.
4. Create the first administrator interactively with `python -m app.cli create-admin`; no default admin credential exists.
5. Review model cards/licenses and institutional policies, install the pinned weights explicitly with `python -m app.cli install-models --accept-model-terms`, then run `python -m app.cli model-check`.
6. Run restore rehearsals and representative device/accessibility/security evaluations. Provide a genuine accessible attendance alternative and a human correction/appeal process before student enrollment.

Use `README.md` and `docs/SETUP.md` for exact Linux and Windows commands. This report records local validation only; it does not claim the untested hardware, platform or deployment paths are production-ready.
