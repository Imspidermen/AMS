# Setup, local development, and deployment

## Supported layout

- Python 3.11 is the validated development interpreter. `backend/requirements.lock` pins runtime and test dependencies; Python 3.11–3.12 is declared. Node.js 22.12+, 24.x, or 26+ is required by the pinned frontend test toolchain (Node 22.22.3/npm 10.9.2 were used for validation). Windows and PostgreSQL are supported by configuration/scripts but were not run in this build environment.
- SQLite is the safe local/test default. The configured development database path is `data/ssams.db`; backend commands that use the default relative SQLite URL should be run with `backend/` as the current directory. On POSIX, the backend sets a restrictive process umask and enforces mode `0600` on SQLite files; on Windows, protect the `data/` directory with user-only ACLs. Pytest uses the separate `data/ssams-tests.sqlite3` database and recreates only that test database.
- PostgreSQL is the production target. Apply schema changes only with Alembic; do not use `create_all` as a production migration mechanism.
- Model files are not bundled in Git. They are obtained explicitly, checked against pinned SHA-256 digests, and then run offline. Read [MODEL_CARD.md](../models/MODEL_CARD.md) first.

## Linux: development setup

From the repository root:

```bash
./scripts/setup_linux.sh
cd backend
.venv/bin/python -m app.cli generate-secrets
cd ..
```

Copy the two generated values into the private root `.env` file, replacing `SESSION_SECRET` and `BIOMETRIC_ENCRYPTION_KEY`. Do not paste them into chat, commit them, or reuse them between environments. Keep the Fernet encryption key in an independent secrets backup; losing it makes existing biometric templates unrecoverable. Do not rotate it without a migration/reenrollment plan.

Configure at least:

```dotenv
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
CAMPUS_TIMEZONE=Asia/Kolkata
DATABASE_URL=sqlite:///../data/ssams.db
SESSION_SECRET=<unique generated value, at least 32 random bytes>
BIOMETRIC_ENCRYPTION_KEY=<generated Fernet key>
COOKIE_SECURE=false
FRONTEND_DIST=frontend/dist
MODEL_DIR=models
```

`CAMPUS_TIMEZONE` is the single source of truth for business time. `Asia/Kolkata` (IST, UTC+05:30) is the default: attendance days, schedule windows, reports, exports, API timestamps and log lines are all expressed in it, while instants are still stored as UTC. Changing it later is a policy decision — existing rows keep their exact instants and are simply re-interpreted.

`APP_HOST`/`APP_PORT` define the **one** public port. The default port-8000 server serves the built React app at `/` and the API at `/api`, so no CORS entry is needed (`CORS_ORIGINS` is empty by default and only used for a deliberate cross-origin deployment).

The `.env` path is loaded from the repository root. The default SQLite URL is relative to the backend process working directory. Do not expose the development server to an untrusted network.

Start the unified application (one port) from the repository root:

```bash
./scripts/run_linux.sh
```

The script builds `frontend/dist` when needed, applies Alembic migrations, and starts FastAPI on `APP_HOST:APP_PORT` (`0.0.0.0:8000` by default). It serves the React application at `http://localhost:8000/` and the API at `http://localhost:8000/api/v1` — the same single port a tunnel should expose. Use a separate terminal for the first admin bootstrap:

```bash
cd backend
.venv/bin/python -m app.cli create-admin
```

The CLI prompts for the administrator email, name, and password and refuses to create a second bootstrap administrator. There are no default production credentials.

Equivalent manual commands:

```bash
# Terminal 1 — build once, then review/migrate the database
cd frontend && npm run build
cd ../backend
.venv/bin/python -m app.cli migrate
.venv/bin/python -m app.cli serve            # frontend + API on APP_PORT from the root .env
```

### Development mode (Vite hot reload)

The Vite workflow is unchanged and still recommended while editing frontend code. Vite proxies `/api` to the backend (target `SSAMS_API_TARGET`, otherwise `http://127.0.0.1:$APP_PORT`), so the browser only ever uses one origin:

```bash
./scripts/dev_linux.sh
```

```bash
# Terminal 1
cd backend
.venv/bin/python -m app.cli migrate
.venv/bin/python -m app.cli serve

# Terminal 2
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

Open `http://localhost:5173` in development; open `http://localhost:8000` for the unified/production-style application and for tunnels.

## Native Windows PowerShell

Install Python 3.11, Node.js/npm, and Git. From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
Set-Location .\backend
.\.venv\Scripts\python.exe -m app.cli generate-secrets
Set-Location ..
```

Edit `.env`, replace both secrets, then start the **unified single-port** application (it builds the frontend when `frontend\dist` is missing, migrates the database, and serves everything on `APP_PORT`):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_windows.ps1
```

Open `http://localhost:8000`. For the two-process Vite development workflow instead (Vite on 5173 with `/api` proxied to the API), use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev_windows.ps1
```

The unified script stays in the foreground and stops with `Ctrl+C`. Bootstrap the first admin from another window:

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m app.cli create-admin
```

The same Alembic, API, and React code is used on Linux and Windows. These native Windows commands are not verified on Windows; see the limitations in [BUILD_STATUS.md](BUILD_STATUS.md). For PowerShell model download/checksum commands, follow the model installation section below.

## PostgreSQL production configuration

Create a dedicated PostgreSQL role and a new database using your DBA's approved process. Example on a local Linux PostgreSQL host:

```bash
sudo -u postgres createuser --login --pwprompt ssams_app
sudo -u postgres createdb --owner=ssams_app ssams
```

Enter a unique secret at the interactive prompt. In the private root `.env`, set a PostgreSQL SQLAlchemy URL and production settings (URL-encode special characters in the username/password):

```dotenv
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
DATABASE_URL=postgresql+psycopg://ssams_app:<URL-ENCODED-SECRET>@127.0.0.1:5432/ssams?sslmode=verify-full
COOKIE_SECURE=true
CAMPUS_TIMEZONE=Asia/Kolkata
FRONTEND_DIST=frontend/dist
MODEL_DIR=models
CORS_ORIGINS=https://attendance.example.edu
```

A production deployment has two supported shapes:

1. **Single-port application** — keep `APP_HOST=0.0.0.0`/`APP_PORT=8000`, run `python -m app.cli serve`, and let the institution's TLS terminator/tunnel forward to that one port. The frontend is served from the same origin as the API, so cookies are same-site and `CORS_ORIGINS` can stay empty.
2. **Reverse proxy with static frontend** — bind Uvicorn to loopback (`APP_HOST=127.0.0.1`) and let Nginx serve `frontend/dist` at `/` while proxying `/api/` to the backend, as shown in [`deployment/`](../deployment/). Set `CORS_ORIGINS` only if the browser really loads the app from another origin.

Use a separate secrets manager/environment file readable only by the service account; do not use the example URL/password as a credential. Configure PostgreSQL TLS and verify its CA, restrict network access, and back up the database and both application keys independently. Run migrations from `backend/` using the production virtual environment before deploying the new application version:

```bash
.venv/bin/python -m app.cli migrate
.venv/bin/python -m app.cli create-admin  # only for the first administrator
```

A basic Nginx/systemd example is in [`deployment/`](../deployment/). It is a template: replace the host, paths, TLS certificates, service user, and secret-file permissions. Keep Uvicorn bound to loopback behind TLS termination; do not expose port 8000 directly to phones or the public Internet. Back up and test a restore before a production release.

For PostgreSQL backups, install the matching PostgreSQL client tools (`pg_dump`/`pg_restore`) on the host. The Python driver alone does not supply those executables.

## Alembic migration workflow

```bash
cd backend
.venv/bin/python -m app.cli migrate        # upgrade to head
.venv/bin/python -m alembic current        # show the applied revision
.venv/bin/python -m alembic heads          # show repository heads
.venv/bin/python -m alembic check          # detect model/schema drift
```

Always take a verified backup before applying a production migration. Alembic may be rolled forward by deploying a tested corrective migration; do not delete or recreate a production database to solve a migration error.

## Local face/liveness model installation (online once, offline after)

Review [the model card](../models/MODEL_CARD.md) and obtain institutional approval before enrolling users. The installer refuses to run without explicit `--accept-model-terms` and verifies every downloaded file before atomically installing it. From `backend/`:

```bash
.venv/bin/python -m app.cli install-models --accept-model-terms
.venv/bin/python -m app.cli model-check
```

The models are saved under `models/`; startup does not download them. `model-check` validates hashes and initializes OpenCV/MediaPipe locally on CPU. If an upstream network/TLS route is unavailable, download from the immutable source revisions in `MODEL_CARD.md`, transfer via an approved secure channel, and verify before placing the files in the configured `MODEL_DIR`:

```bash
# Linux/macOS — run from the repository root; use the exact pinned URLs in MODEL_CARD.md.
mkdir -p models
curl --fail --location --output models/face_detection_yunet_2023mar.onnx 'https://media.githubusercontent.com/media/opencv/opencv_zoo/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet/face_detection_yunet_2023mar.onnx'
curl --fail --location --output models/face_recognition_sface_2021dec.onnx 'https://media.githubusercontent.com/media/opencv/opencv_zoo/ba91a3b91d00d76e86540d4013f944bd6b514e39/models/face_recognition_sface/face_recognition_sface_2021dec.onnx'
sha256sum -c models/SHA256SUMS
```

PowerShell equivalent:

```powershell
New-Item -ItemType Directory -Force .\models | Out-Null
Invoke-WebRequest -Uri 'https://media.githubusercontent.com/media/opencv/opencv_zoo/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet/face_detection_yunet_2023mar.onnx' -OutFile .\models\face_detection_yunet_2023mar.onnx
Invoke-WebRequest -Uri 'https://media.githubusercontent.com/media/opencv/opencv_zoo/ba91a3b91d00d76e86540d4013f944bd6b514e39/models/face_recognition_sface/face_recognition_sface_2021dec.onnx' -OutFile .\models\face_recognition_sface_2021dec.onnx
Get-FileHash .\models\face_detection_yunet_2023mar.onnx -Algorithm SHA256
Get-FileHash .\models\face_recognition_sface_2021dec.onnx -Algorithm SHA256
```

Compare PowerShell output exactly with `models/SHA256SUMS`; never bypass a mismatch. Re-run `model-check` after copying. Once installed, inference makes no network calls. Model installation itself was not completed in this environment because previous model-download attempts failed with TLS/SSL EOF errors; no biometric model inference is claimed as tested.

## Phone/tablet access and HTTPS

Browser camera and geolocation APIs require a **secure context**. `http://localhost` is treated specially on the development device, but a phone accessing `http://<computer-LAN-IP>:5173` is not a secure context. For a phone:

1. Use an institution-controlled DNS name and a trusted TLS certificate, with Nginx/IIS or an approved TLS gateway serving the frontend and proxying `/api/` to Uvicorn. For quick testing on your own machine, a tunnel is enough: build the frontend, run `python -m app.cli serve`, then `ngrok http 8000` and open the resulting `https://…` URL — the app, `/api/*` and `/docs` all live on that one port, and phones get a secure context for the camera/geolocation.
2. Use the same HTTPS origin for frontend and API so session cookies remain same-site. Set `APP_ENV=production` or `COOKIE_SECURE=true`; configure `CORS_ORIGINS` only for explicitly used cross-origin origins.
3. Permit camera and location for that HTTPS origin in the mobile browser and OS settings. SSAMS requests a location only after a student starts an eligible attendance attempt; do not rely on indoor GPS accuracy.
4. For local development only, Vite can use `SSAMS_DEV_TLS_KEY` and `SSAMS_DEV_TLS_CERT` configured in `frontend/.env.local` (see `frontend/.env.example`). Install/trust the issuing development CA on the phone; do not use a self-signed certificate users cannot validate.
5. For a quick device test without any certificate work, use the unified port plus a tunnel (`python -m app.cli serve` then `ngrok http 8000`): the tunnel terminates TLS, so the browser gets the secure context that camera and geolocation require.

The Vite proxy points at `http://127.0.0.1:8000` from the **development server**, not from the user's browser. Production requests should use relative `/api/v1` paths through the configured reverse proxy.
