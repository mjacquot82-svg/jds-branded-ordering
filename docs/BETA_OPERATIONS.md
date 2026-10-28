# Beta operations (2–3 shop beta)

Nothing here is live until Marc enables it. No accounts are created by this change.

## 1. Nightly database backup
- Script: `scripts/ops/backup_db.sh` — `pg_dump --format=custom`, encrypted with GPG (AES256, passphrase),
  14-day local retention, optional off-site copy via `rclone` (`BACKUP_RCLONE_REMOTE`).
  Verified locally: dump → decrypt → `pg_restore` into an empty DB round-trips all tables.
- Free scheduler: `.github/workflows/nightly-db-backup.yml` runs 03:15 Toronto and stores the encrypted dump as
  a 14-day GitHub Actions artifact (off the app server). It is **skipped** unless repo variable
  `BACKUPS_ENABLED=true`. To enable, Marc adds repo secrets `BACKUP_DATABASE_URL` (a read-only DB role is
  preferred) and `BACKUP_PASSPHRASE` (store it in a password manager — without it backups can't be restored).
  Note: the DB must accept connections from GitHub runners (Supabase does by default; Canner Postgres needs
  external access enabled). If Canner can't allow that, run the same script from a Canner scheduled job/cron.
- Restore: `gpg -d FILE | pg_restore --clean --if-exists --no-owner -d "$TARGET_URL"`. Test a restore monthly.

## 2. Photos off the app server
- Preferred (no new code): `JDS_MEDIA_STORAGE=supabase` with a private bucket (`backend/app/platform/media.py`).
  Photos then live in Supabase Storage, not on the Canner disk. Choose a Canadian region at project creation if
  offered (verify at signup).
- If photos stay on Canner disk (`JDS_MEDIA_STORAGE=local`, `JDS_LOCAL_MEDIA_ROOT`), run
  `scripts/ops/sync_media_offsite.sh` nightly to copy them to any S3-compatible bucket via rclone (`copy`, never
  `sync`, so off-site copies survive local loss). Bucket provider not chosen; free tiers exist but none verified.

## 3. "Report a problem"
- Set `VITE_REPORT_PROBLEM_URL` at web build time to `mailto:<address>` or an `https://` form URL.
  The link appears in the customer footer and the shop admin dashboard. Unset/invalid → hidden.

## 4. Uptime monitoring (free)
- Endpoints: `GET /health/live` (process up) and `GET /health/ready` (DB reachable, 503 otherwise).
- Use any free uptime checker (e.g. UptimeRobot or Better Stack free plans — check current limits at signup):
  1. HTTP monitor on `https://<api-host>/health/ready`, 5-minute interval, alert email to Marc.
  2. HTTP monitor on the web origin `/` (expects 200).
  3. Optionally a keyword monitor on `/health/ready` for `"database": "ok"`.
- On Canner Starter the app sleeps when idle; a 5-minute monitor keeps it awake, which may conflict with
  Starter limits — another reason to use Live for testers.
