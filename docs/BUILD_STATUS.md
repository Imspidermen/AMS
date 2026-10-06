# SSAMS build and validation status

**Status as of 2026-10-06:** implementation and Linux-hosted automated validation are complete for the features listed below. This is not a production certification. Native Windows, PostgreSQL, model inference, phone sensors, and institutional/legal review remain unverified.

## Repository and environment

- Built in `/home/user/AMS` on branch `arena/05b234d0-ams` from an initially empty application repository (the starting repository contained the MIT license only).
- Validation environment: Linux x86_64, Python 3.11, Node.js 22.22.3, npm 10.9.2. PostgreSQL client/server tools and PowerShell are not installed.
- Backend tests use the isolated, ignored SQLite database `data/ssams-tests.sqlite3`. `data/ssams.db` is the local development database and is not used as a disposable test target.
- Production database support is implemented for PostgreSQL, but no PostgreSQL installation was available here.

## Implemented scope

- FastAPI/SQLAlchemy backend, Alembic migrations, SQLite local/test and PostgreSQL deployment configuration.
- Admin, Teacher, and Student authorization and workflows; password hashing, opaque server-managed sessions, CSRF protections, account activation/reset, audited corrections, academic setup, schedules, enrollment, locations, attendance, notifications, CSV/print reporting, and campus-timezone handling.
- Server-side schedule, enrollment, geofence, challenge, template and face-score checks; transactional/idempotent attendance writes; encrypted face embeddings; UTC server timestamps.
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
