# SSAMS Installation Guide — Windows 11

Everything below runs on Windows 10/11. You do **not** have to change your Windows timezone: the
application always uses **Asia/Kolkata (IST, UTC+05:30)** for attendance days, reports and
displayed times, and stores the exact moment internally as UTC.

## One-time setup

Open **PowerShell** (normal window is fine) and run these commands one by one.

### 1. Go to the project folder

```powershell
Set-Location G:\AMS
```

(Using CMD instead? `cd /d G:\AMS`.)

### 2. Install dependencies

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

This creates `backend\.venv`, installs the Python packages, runs `npm ci` for the frontend and
copies `.env.example` to `.env`.

### 3. Generate secret keys

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m app.cli generate-secrets
Set-Location ..
```

Paste the two generated values into `G:\AMS\.env` for `SESSION_SECRET` and
`BIOMETRIC_ENCRYPTION_KEY`. Keep them private and back up the biometric key separately.

Check the rest of `.env` — the important defaults are already correct:

```dotenv
APP_HOST=0.0.0.0
APP_PORT=8000
CAMPUS_TIMEZONE=Asia/Kolkata
FRONTEND_DIST=frontend/dist
COOKIE_SECURE=false
```

### 4. Build the frontend

```powershell
Set-Location .\frontend
npm run build
Set-Location ..
```

(`scripts\run_windows.ps1` also does this automatically the first time.)

## Start the application (one port)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_windows.ps1
```

The script builds `frontend\dist` if needed, applies database migrations and serves the whole
application — React frontend **and** backend — on the single port from `.env` (8000 by default).
Leave this window open.

## Create the admin account

Open a second PowerShell window:

```powershell
Set-Location G:\AMS\backend
.\.venv\Scripts\python.exe -m app.cli create-admin
```

## Open the website

```text
Application : http://localhost:8000
API         : http://localhost:8000/api/v1
API docs    : http://localhost:8000/docs
Health      : http://localhost:8000/api/health
```

`http://localhost:8000` shows the login page; after signing in you get the admin/teacher/student
workspace. Attendance times are shown in IST (for example `07 Oct 2026, 8:30 pm`).

## Share it with phones / test the camera (ngrok)

Camera and location need an **HTTPS** address. Expose the one port with a tunnel:

```powershell
ngrok http 8000
```

Open the generated `https://…ngrok-free.app/` URL. On the first visit ngrok may show an
"Visit Site" page — click it. Then:

1. Open the same URL on the phone.
2. Allow camera and location for that site.
3. Sign in as a student, choose an open class session and mark attendance — the recorded time is
   stored as the exact instant and displayed in IST.

For HTTPS, set `COOKIE_SECURE=true` in `.env` and restart the app (or set `APP_ENV=production`).

Only **one** tunnel is needed — never expose port 5173 separately.

## Day-to-day commands

```powershell
# Restart the unified application
powershell -ExecutionPolicy Bypass -File .\scripts\run_windows.ps1

# Rebuild the frontend after changing frontend code, then restart
powershell -ExecutionPolicy Bypass -File .\scripts\run_windows.ps1 -Rebuild

# Development mode (hot reload): API on 8000 + Vite on 5173 (Vite proxies /api)
powershell -ExecutionPolicy Bypass -File .\scripts\dev_windows.ps1
# then open http://localhost:5173

# Check the application timezone and today's IST boundaries
Set-Location .\backend
.\.venv\Scripts\python.exe -m app.cli timezone-check

# Apply a new database migration
.\.venv\Scripts\python.exe -m app.cli migrate

# Verify the installed face models (optional, after installing weights)
.\.venv\Scripts\python.exe -m app.cli model-check
```

## Notes

- Face enrollment and attendance verification additionally require the pinned local model files:
  review `models\MODEL_CARD.md`, then run
  `.\.venv\Scripts\python.exe -m app.cli install-models --accept-model-terms` from `backend\`.
- The database file lives at `G:\AMS\data\ssams.db` (SQLite) unless you configure PostgreSQL via
  `DATABASE_URL`. Back it up with `python .\scripts\backup_db.py`.
- For production use, follow `docs\SETUP.md` (PostgreSQL, TLS, reverse proxy, backups) instead of a
  tunnel.
