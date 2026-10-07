# Operations, backup, restore, and support

## Operational controls

- Apply the Alembic upgrade for each release after taking and verifying a private database backup. Keep one active Alembic head and deploy backend/frontend code from the same tested release.
- Monitor `/api/v1/health/ready` from a trusted network. It checks database connectivity and reports whether pinned vision files pass their SHA-256 checks; it does not prove the model's demographic performance or end-to-end attendance behavior.
- Run `python -m app.cli model-check` after installing/replacing model files, the Python/OpenCV/MediaPipe environment, or the host CPU runtime. A successful load is a dependency check, not recognition validation.
- Configure an institutional timezone using an IANA identifier, e.g. `Asia/Kolkata` (the default). Timestamps are stored as UTC **instants**; every business rule and every output uses the campus timezone: attendance days and "today", lateness, schedule windows, report/export boundaries, API timestamps, log lines and printed reports. Attendance date filters (`?start=`/`?end=`, `?from_date=`/`?to_date=`) treat a bare date as a campus calendar day, so 23:59 IST stays on the Indian date even when the host clock is still on the previous UTC day.
- Verify the effective timezone after any deployment: `python -m app.cli timezone-check`, `GET /api/health`, or the Admin *Policy & health* screen. The API reports `campus_timezone` and `campus_utc_offset` (e.g. `Asia/Kolkata`, `+05:30`). Never "fix" a timezone problem by editing timestamps in the database.
- The application serves the built frontend and the API on one port (`APP_HOST`/`APP_PORT`, default `0.0.0.0:8000`). Monitor `/api/health` and `/api/v1/health/ready` on that port; only that port needs to be exposed by a reverse proxy or tunnel.
- Monitor disk space, API health, database availability, failed login/verification rates, correction queues, and audit access. Do not send biometric/GPS data into metrics or alerts.
- Use rate-limited, private delivery for account activation/reset links. SSAMS returns the one-time link to the authorized administrator; it does not send email/SMS itself.

## Database backup

Back up before migrations and according to campus recovery-point objectives. The helper reads `.env` and supports SQLite through the SQLite online backup API and PostgreSQL through `pg_dump` custom archives. Existing output files are never overwritten. PostgreSQL deployments must install a compatible `pg_dump` executable separately.

From the repository root, after installing backend dependencies:

```bash
cd backend
.venv/bin/python ../scripts/backup_db.py --output ../data/ssams-$(date -u +%Y%m%dT%H%M%SZ).backup
```

On Windows PowerShell (from the repository root):

```powershell
$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
.\backend\.venv\Scripts\python.exe .\scripts\backup_db.py --output ".\data\ssams-$Stamp.backup"
```

The file is a SQLite database copy or a PostgreSQL custom-format archive based on `DATABASE_URL`. It is **not encrypted** by the helper. Restrict permissions, encrypt before off-host transfer/storage, keep it out of source control, and protect it at least as carefully as the source database. The configured biometric encryption key is not included; store/restore that key independently.

For a direct offline SQLite check, `sqlite3 <backup-file> 'PRAGMA integrity_check;'` should print `ok`. For PostgreSQL, `pg_restore --list <backup-file>` should list archive contents. Do not use either check as a substitute for a restore rehearsal.

## Safe restore rehearsal

Restore only to a new empty database. The helper requires `--confirm-target` to exactly match the target database name in the private `.env`. It refuses to overwrite an existing SQLite target and refuses a PostgreSQL database that already contains tables; it does not execute `DROP` or `--clean`.

1. Take and preserve a backup of the current environment.
2. Create a new test database/file and set `DATABASE_URL` to that target in a private environment file (do not change production traffic).
3. Confirm that the target is empty; pass the exact database name in the second confirmation argument.
4. Restore the backup, run `alembic current` and `alembic check`, perform role-scoped read-only smoke checks, then dispose of the rehearsal database under policy.

Example (SQLite target, repository root; use a previously copied backup file):

```bash
# Configure DATABASE_URL=sqlite:///../data/ssams-restore-test.db in the private .env.
cd backend
.venv/bin/python ../scripts/restore_db.py --source ../data/ssams-20261006T000000Z.backup --confirm-target ssams-restore-test.db
.venv/bin/python -m alembic current
.venv/bin/python -m alembic check
```

Example (PostgreSQL): provision a new empty database, point `DATABASE_URL` at it, then:

```bash
cd backend
.venv/bin/python ../scripts/restore_db.py --source ../data/ssams-production.backup --confirm-target ssams_restore_test
.venv/bin/python -m alembic current
.venv/bin/python -m alembic check
```

The helper intentionally does not modify the database URL and does not create/drop PostgreSQL databases. Treat a failed partial restore as a disposable **new test database** and recreate that test database through your DBA process; never aim the rehearsal at production.

## Incident and account response

- Deactivate compromised/inactive users in Admin People; issue a password reset. Use `logout-all` through an authorized response process if sessions must be revoked globally.
- Review administrator audit events for account, course, location, attendance, correction, and face-template actions. Audit data contains operational context and still requires access control.
- If a face template must be removed, use the student's profile or admin reset action and document the request through approved institutional procedure. Ensure backup expiry also meets deletion policy.
- If a verification is rejected, do not ask the student to repeatedly retry through a failing sensor. Review the API failure reason and assigned session, help the student use the approved alternate attendance process, and document the resolution.
- If keys may be exposed, restrict access and follow incident/key-rotation response. `BIOMETRIC_ENCRYPTION_KEY` rotation cannot be performed by changing `.env` alone; existing encrypted templates need a controlled decrypt/re-encrypt migration or reenrollment.

## Help desk boundaries

SSAMS is an in-app tool; it has no hosted cloud account, outbound SMS, external email sender, or remote model endpoint. Institutions must publish a real attendance/privacy contact, accessible non-biometric alternative, camera/location troubleshooting, and correction escalation path before inviting students.
