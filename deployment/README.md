# Deployment templates

`nginx/ssams.conf`, its `nginx/security-headers.conf` include, and `systemd/ssams-api.service` are starting templates for a Linux PostgreSQL deployment. The Nginx include is referenced at `/opt/ssams/deployment/nginx/security-headers.conf`; update that path if the release is installed elsewhere. They are not production-ready unchanged: replace `attendance.example.edu`, TLS paths, application location, dedicated service account, database/secret settings, retention, monitoring, backup location, and firewall rules. Review them with the institution's infrastructure/security team. Native Windows production should use the institution's hardened IIS/reverse-proxy/TLS setup; `scripts/run_windows.ps1` is development-only.

## Linux deployment outline

1. Create a dedicated unprivileged `ssams` account and install a supported Python/Node toolchain, PostgreSQL, Nginx, and matching PostgreSQL client utilities.
2. Deploy this source tree to `/opt/ssams` with controlled ownership. Install backend dependencies in `/opt/ssams/backend/.venv`, install frontend dependencies, and build `frontend/dist` with `npm run build`.
3. Configure `/etc/ssams/ssams.env` as a root-owned, mode-`0600` environment file with `APP_ENV=production`, `APP_HOST=127.0.0.1`, `APP_PORT=8000`, a PostgreSQL SQLAlchemy URL, `SESSION_SECRET`, `BIOMETRIC_ENCRYPTION_KEY`, `COOKIE_SECURE=true`, `CAMPUS_TIMEZONE=Asia/Kolkata`, `FRONTEND_DIST=/opt/ssams/frontend/dist`, `MODEL_DIR=/opt/ssams/models`, and explicit origins only if the browser really uses another origin. Use a secret manager where available. `CAMPUS_TIMEZONE` is the application timezone for attendance days, reports, exports, API timestamps and logs; the service unit also exports `TZ=Asia/Kolkata` so log line formatting matches on a UTC host. The host system timezone does not need to change.
4. Install and check local model weights in `/opt/ssams/models`; review `models/MODEL_CARD.md` and maintain license notices. Apply Alembic migrations and create the first administrator interactively before enabling traffic.
5. Expose **one** public port. Either keep the Nginx template (it serves `frontend/dist` and proxies `/api/` to Uvicorn) or, for a simpler deployment, run the unified server (`python -m app.cli serve` with `APP_HOST=0.0.0.0` and `APP_PORT=8000`) and point the TLS terminator or tunnel straight at that single port — FastAPI then serves the built SPA itself, including the `index.html` fallback for deep links. Configure Nginx with a valid institutional TLS certificate and the reviewed `ssams.conf`; install/enable the systemd service after editing its paths/account. Verify TLS headers, same-origin `/api/v1`, reverse-proxy `Host`/`X-Forwarded-Proto`, `/api/health`, `/api/v1/health/ready` (it reports the effective `campus_timezone` and offset), readiness, cookies, and frontend route fallback.
6. Restrict port `8000` to loopback and PostgreSQL to its application network. Expose only the TLS reverse proxy to intended campus devices; apply firewall/rate limiting and security updates.
7. Rehearse a backup/restore in a separate empty database. Protect DB dumps and encryption/session secrets independently.

The service template runs one Uvicorn worker to bound CPU/memory use and uses loopback proxy headers. Capacity-test before changing workers. `ProtectSystem=strict` assumes PostgreSQL (not SQLite) and that the installed application/models are read-only to the service account. Adjust sandbox restrictions only through a reviewed deployment change.

## Development note

The provided Linux/Windows run scripts use the Vite development server and HTTP defaults. They are not suitable for production and must not be used as a public TLS termination layer.
