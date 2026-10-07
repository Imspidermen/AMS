# Troubleshooting

## App will not start / schema missing

1. Confirm `.env` exists at repository root, both secret values are set, and its file permissions restrict access.
2. Use the backend virtual environment and the backend working directory:
   ```bash
   cd backend
   .venv/bin/python -m app.cli migrate
   .venv/bin/python -m app.cli serve        # unified: frontend + API on APP_PORT
   ```
3. Check `/api/health` and `/api/v1/health/ready` and logs for a generic request ID. Do not paste `.env`, cookies, liveness tokens, activation/reset URLs, or face/GPS payloads into a support ticket.
4. Use `alembic current`, `alembic heads`, and `alembic check`; take a backup before any repair. Never delete the production database to fix a migration mismatch.

## Sign-in, activation, or CSRF errors

- Verify the account is active and an administrator has completed the correct activation flow. The invitation/reset token expires and is one-time; request a new link if it expired.
- The application requires a matching `SESSION_SECRET` on API workers. Changing it invalidates sessions; use a coordinated restart.
- Authenticated mutations require the same-origin CSRF cookie and header. Clear stale site cookies and sign in again if the cookie/session pair no longer matches.
- Check system time, reverse-proxy cookie forwarding, same-site origin, and production `COOKIE_SECURE=true` only when the browser uses HTTPS. Do not weaken CSRF or cookie flags to work around deployment errors.
- There is no preconfigured administrator password. Create the first administrator using the interactive CLI after migrations.

## Camera or location unavailable on phones

- Camera and geolocation require a secure HTTPS origin with a trusted certificate. Plain LAN HTTP is not sufficient. `http://localhost` is a development exception on the computer, not on another device.
- Grant this site camera/location permission in both the browser and OS. Use a current browser, turn off other camera-consuming apps, and ensure camera hardware is not blocked by device policy.
- Indoor geolocation may be unavailable or inaccurate. Move to a permitted location with clearer satellite reception or use the institution's approved alternate attendance process; never weaken server geofence policy to force acceptance.
- On a challenge failure, start a new attempt. The server expires and consumes challenges and rate-limits repeated attempts. Do not replay camera recordings as a workaround.

## Face enrollment/verification unavailable

- `GET /api/v1/health/ready` or the Admin readiness screen shows model file/checksum status. `face/status` fails closed when an expected weight is missing or has the wrong digest.
- Review the model card and license inventory, explicitly install the pinned models, then run `python -m app.cli model-check` from `backend/`. The check loads OpenCV YuNet/SFace and MediaPipe locally.
- If the download fails with TLS, proxy, or SSL EOF errors, use the offline transfer steps in [SETUP.md](SETUP.md). Verify the exact SHA-256 before copying; never rename an unrelated ONNX model to match the expected filename.
- `BIOMETRIC_ENCRYPTION_KEY` must be a valid Fernet key and must remain available. Do not regenerate it for an existing database; key loss prevents decryption of enrolled templates.
- Face mismatch, poor lighting, blur, multiple faces, poor pose, missing face, liveness expiry, and model errors are separate failure paths. A failed attempt does not write attendance; follow the institution's manual review/alternate attendance policy.

## Times or the attendance day look wrong

- The application timezone is `CAMPUS_TIMEZONE` in the root `.env` (default `Asia/Kolkata`, IST). Timestamps are stored as UTC instants and converted for every output, so a database row will not look like the value on screen — that is expected. Use `GET /api/health`, `/api/v1/health/ready`, the Admin *Policy & health* screen, or `python -m app.cli timezone-check` to see the effective zone and offset.
- Only `Asia/Kolkata`, `Asia/Calcutta` or a different valid IANA name belongs here; `+05:30`, `IST5` or `330` are not valid IANA names and are rejected at startup.
- Attendance date filters use campus days: `?start=2026-10-07&end=2026-10-07` covers 00:00–23:59 IST of 7 October (18:30 UTC on 6 October → 18:30 UTC on 7 October). That is why an early-morning UTC row can belong to the previous Indian date — the API also returns `marked_on_ist` so you do not have to compute it.
- CSV exports and the printable report are IST by default (`marked_on_ist`, `marked_at_ist`, "Recorded at (IST)"). If a spreadsheet shows a different day, check its own timezone settings before changing the application.
- The Windows system timezone does not need to be (and should not be) changed. Nothing in the application reads the host timezone for business logic; only log line formatting follows it.

## One port / tunnel problems (ngrok, Cloudflare Tunnel)

- Serve the unified application (`scripts/run_windows.ps1`, `scripts/run_linux.sh`, or `python -m app.cli serve`) and expose **only** `APP_PORT` (default 8000): `ngrok http 8000`. Never start a second tunnel for the Vite dev port.
- Check `http://localhost:8000/`, `/api/health` and `/docs` locally first: if those work, a failing public URL is a tunnel issue, not an application issue.
- ngrok's free tier shows a one-time browser interstitial page ("Visit Site") for new visitors — click it and the application loads normally; API/XHR requests are unaffected.
- Set `COOKIE_SECURE=true` when the public URL is HTTPS so session cookies are marked Secure. `APP_ENV=production` does this automatically. Do not enable it while testing plain `http://localhost`, or the browser will drop the session cookie.
- Keep the tunnel authenticated/private for biometric use; a public URL means the login page — and the camera flow — is reachable by anyone who finds it.
- If the frontend loads but a deep link (for example `/admin/audit`) returns a page error, confirm the build is present (`frontend/dist/index.html`) and that the reverse proxy forwards unknown paths to the application instead of returning its own 404.
- If `/api/...` returns HTML instead of JSON, something is serving the SPA for API paths: the application never does that (unknown `/api/*` paths return a JSON 404), so check the proxy's route ordering.

## Vite API proxy or CORS errors

- The browser calls relative `/api/v1/...` endpoints. Vite forwards `/api` to `http://127.0.0.1:$APP_PORT` (root `.env`, default 8000) from the dev server; start both processes and keep that port reachable locally.
- If the API is on another host/port, set `SSAMS_API_TARGET` in the root `.env` or `frontend/.env.local` before starting Vite. The browser must still use relative URLs; never point browser code at `localhost:8000` for another origin.
- In unified mode (and through a tunnel) the frontend and the API share one origin, so no CORS configuration is required; `CORS_ORIGINS` is empty by default and adding a wildcard would be rejected anyway because sessions use credentialed cookies.
- For a genuine cross-origin deployment, explicitly list the exact HTTPS origin in `CORS_ORIGINS`; prefer a same-origin reverse proxy.
- Vite's broad `allowedHosts` setting is development-preview convenience only. Do not use Vite as an Internet-facing production server.

## PostgreSQL or backup utilities

- Confirm PostgreSQL is reachable using configured TLS/CA, the account has only the required application privileges, and `DATABASE_URL` is correctly URL-encoded. Apply migrations from `backend/`.
- `pg_dump` and `pg_restore` are system tools; install a client version compatible with the server. Python's `psycopg` wheel does not contain them.
- The restore tool requires a new empty target and exact `--confirm-target`. It does not overwrite tables; recreate a failed test target through the database administrator before retrying. Do not point restore at production.
- Backups contain student, attendance, audit, and encrypted biometric data and are not encrypted by the helper. Protect the file and encryption key separately; perform a restore drill.

## Native Windows notes

- Use the scripts from an ordinary PowerShell prompt with Python 3.11, Node.js/npm and the pinned packages installed. A policy/permission error may require an institution-approved execution policy; do not disable machine-wide protections.
- Open the API/Frontend terminal windows and read their logs separately. Confirm Windows Firewall allows only the intended trusted campus network and do not expose the development HTTP URL to students for biometric access.
- Native Windows install, browser camera hardware, Windows geolocation drivers, PostgreSQL and TLS behavior were not validated in the Linux build environment. Escalate platform-specific errors with version details after removing secrets/personal data.
