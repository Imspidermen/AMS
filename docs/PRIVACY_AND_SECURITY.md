# Privacy, security, and operating boundaries

## Sensitive data inventory

| Data | Purpose | Stored by SSAMS | Primary access boundary |
|---|---|---|---|
| Account email, role, account status, student/employee IDs and academic assignments | Account administration and role-based workflows | Yes | Server-side role and resource scope; admin manages accounts, teacher access follows assigned courses/sections, student reads self records |
| Password | Login | Argon2id hash only | Never returned by API or shown in UI |
| Session token | Authenticated requests | Hash in `user_sessions`; opaque token in HttpOnly cookie | Same-site cookie, expiration, revocation, and session-bound CSRF validation |
| CSRF token | Protect authenticated mutations | Hash bound to session; browser-readable CSRF cookie | Same-origin `X-CSRF-Token` header validation |
| Encrypted face embedding | 1:1 comparison with that student's live frame | Fernet-encrypted vector in DB; Fernet key is a separate secret | Role-checked student owner/admin reset; do not put the key in the database or backups stored with it |
| Raw camera frames | Enrollment/verification processing | Not intentionally persisted to SSAMS database or logs; frames are read and processed in memory | Browser consent and permissions; API upload-size limit; do not add frame/body logging |
| Liveness progress | Temporal challenge | Temporary challenge actions, counters, timestamps, a digest of the most recent frame, and completion/consumption state | Challenge is bound to user/session and token; expire and clean under an institution-set retention policy. Digest/progress are still sensitive metadata |
| Geofence check | Verify reported point against configured classroom boundary | The student's raw latitude/longitude are not stored; distance, reported accuracy, measurement time, outcome/reason, and location/session references are retained | Server rechecks geofence and freshness; browser coordinates are untrusted and spoofable |
| Attendance, correction, notification, audit events | Institutional attendance, appeal, accountability | Yes; server timestamps in UTC | Student self-only; teacher assigned-course scope; admin scope. Attendance/audit are not automatically erased by cleanup |

Review the actual model and migration code for the release you deploy. The web privacy notice is a starting template and must be customized to campus retention, support, legal basis, accessibility, and alternative attendance processes.

## Security properties implemented

- Argon2id password hashing; activation/reset tokens are one-time and expire; admin bootstrap refuses a second first-admin creation.
- Server-managed opaque sessions use an HttpOnly cookie. State-changing authenticated routes enforce a session-bound double-submit CSRF check. Mutations are role-checked on the server, not just hidden in React routes.
- Teacher API scope is validated against course/section assignments. Student attendance/history/corrections/profile are limited to the signed-in student's own record. Admin attendance corrections require a reason and write an audit event.
- Attendance uses a database uniqueness constraint/transaction and an idempotency key; server time, enrollment, session schedule, geofence, challenge state, and the student's encrypted template are checked before committing.
- Model files are explicitly downloaded from pinned revisions and SHA-256 verified; model loading fails closed when files/hashes are missing or invalid. No runtime model fetch is implemented.
- POSIX backend, SQLite, backup, and restore processes use a restrictive `umask`; SQLite database and SQLite backup/restore files are enforced to mode `0600`. On Windows, the `data/` directory and backups must be protected with user-only ACLs.
- API exception responses use generic errors; audit events intentionally omit passwords, session/cookie values, raw frames, embedding values, and raw coordinates. Review reverse-proxy/APM/access-log configuration so it does not record request bodies, secrets, or sensitive query strings.
- CSV fields are protected against spreadsheet formula injection; server-side API uses same-origin paths through a development proxy and must be served behind trusted TLS in production.

These controls reduce risk; they are not a security certification or a guarantee against compromised devices, privileged insiders, database/backup theft, infrastructure misconfiguration, malicious browser extensions, traffic interception, frame injection, or advanced spoofing.

## Biometric and location safeguards before launch

1. Complete an institution-approved privacy-impact and threat assessment. Obtain the required lawful basis/consent and publish an accurate notice, retention schedule, human contact, appeal path, and non-biometric alternative. A checkbox alone does not establish legal sufficiency.
2. Review [MODEL_CARD.md](../models/MODEL_CARD.md), the separate YuNet/SFace licenses, SFace dataset provenance discussion, MediaPipe bundle notices, and threshold calibration. Have institutional counsel evaluate all model/dataset and deployment terms.
3. Validate false-accept and false-reject behavior using an institution-approved, representative and consented protocol. Do not use unvalidated scores as sole evidence for discipline, grading, benefits, or access denial.
4. Use HTTPS with a trusted certificate for every student device; set `APP_ENV=production` (which enables Secure cookies) and restrict firewall ingress. Keep PostgreSQL private and use least-privileged accounts.
5. Store `.env`, `SESSION_SECRET`, and `BIOMETRIC_ENCRYPTION_KEY` in a secrets manager or tightly permissioned secret file. Back up the biometric encryption key separately from the database; test key restoration before enrollment. Key loss makes existing encrypted templates unreadable.
6. Restrict database, audit log, application log, and backup access. Encrypt backups at rest and in transit, define rotation/retention, and test incident response. The backup helper creates a database copy; it does not encrypt it for you.
7. Do not log request bodies, uploaded frames, cookies, authorization headers, liveness tokens, activation/reset query tokens, full raw coordinates, or biometric vectors. Configure reverse proxies/monitoring accordingly.

## Retention and deletion

There is no background job that silently deletes attendance history. `python -m app.cli retention` is a dry run by default, with defaults of 90 days for verification attempts and 30 days for liveness challenges; choose values only after policy approval. It also removes expired sessions when applied. It never deletes attendance records or audit records.

Example dry-run (from `backend/`):

```bash
.venv/bin/python -m app.cli retention --verification-days 90 --challenge-days 30
```

Apply only after review and backup:

```bash
.venv/bin/python -m app.cli retention --verification-days 90 --challenge-days 30 --apply
```

Deleting biometric templates is more consequential and requires the separate flag plus explicit confirmation; it is not enabled by the default cleanup command:

```bash
.venv/bin/python -m app.cli retention --include-biometrics --biometric-days 365 --confirm-biometrics --apply
```

Students may request deletion from their profile; administrators can reset an enrollment. Database deletion does not erase copies in old backups. Apply backup expiry and disposal controls separately.
