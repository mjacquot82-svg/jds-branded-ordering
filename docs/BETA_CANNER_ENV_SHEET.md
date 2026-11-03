# Private beta (2–3 shops) — Canner + Supabase fill-in sheet

Supersedes the branch/values in `CANNER_PILOT_DEPLOYMENT.md` for the beta. Nothing here
is a secret; real values live in Canner's env settings (and an operator-only file on the
ops box), **never in this public repo**.

## Where data lives
- **Database:** Canner Postgres on `jds-beta-api` (Database tab, `DATABASE_URL` injected).
  Schema = Alembic migrations, applied automatically by the release command
  `python -m app.db.migrate`. No Supabase tables, RLS or buckets are used — the API is
  the only DB client and enforces per-shop isolation itself.
- **Supabase project `eeqlrsdwivdypdnynofx` (ca-central-1, free):** sign-in + verification
  emails only.
- **Photos:** `JDS_MEDIA_STORAGE=local` on `$CANNER_DATA_DIR/media` (off-site copy: `scripts/ops/sync_media_offsite.sh`).

## Canner project `jds-beta-api` (root `backend`, branch `main`, PR previews OFF)
| Variable | Value / source |
| --- | --- |
| DATABASE_URL | injected by Canner |
| FRONTEND_URL | `https://<web>.canner.app` |
| PUBLIC_APP_URL | `https://<api>.canner.app` |
| JDS_ENVIRONMENT | `staging` |
| JDS_AUTH_PROVIDER | `supabase` |
| JDS_AUTH_SECURE_COOKIES | `true` |
| JDS_APPLICATION_KEY | `jds-commerce` |
| JDS_STOREFRONT_SCHEME | `https` |
| JDS_PAYMENT_MODE | `review` |
| JDS_OUTBOUND_INTEGRATIONS_ENABLED | `false` |
| JDS_BILLING_ENFORCEMENT_ENABLED | `false` |
| JDS_STANDARD_PLAN_MONTHLY_CAD | `150` |
| JDS_MEDIA_STORAGE | `local` |
| JDS_AUTH_SESSION_PEPPER | secret — operator file |
| JDS_DEMO_INVITE_CODE | secret — operator file |
| SUPABASE_AUTH_URL | `https://eeqlrsdwivdypdnynofx.supabase.co` |
| SUPABASE_AUTH_PUBLISHABLE_KEY | Supabase → Project Settings → API Keys → Publishable key |
| SUPABASE_AUTH_SECRET_KEY | Supabase → Project Settings → API Keys → Secret keys (sensitive) |
| JDS_ORDER_ALERT_FROM_EMAIL | `contact@jdsstudio.ca` (only active once a mail key is set) |
| JDS_ORDER_ALERT_RESEND_API_KEY | leave unset → order alerts skipped, orders unaffected |

## Canner project `jds-beta-web` (root `/`, branch `main`, PR previews OFF)
- Build `npm run build`, start `node scripts/canner-pilot-server.mjs`, health `/`.
- `PILOT_API_ORIGIN=https://<api>.canner.app`
- `VITE_REPORT_PROBLEM_URL=mailto:contact@jdsstudio.ca` (build-time, not secret)

## Supabase dashboard
1. Auth → URL Configuration: Site URL `https://<web>.canner.app`, redirect `https://<web>.canner.app/build/verify`.
2. Auth → Emails: built-in sender is rate-limited (few/hour) and comes from Supabase; fine
   for 2–3 testers. Sending from contact@jdsstudio.ca needs custom SMTP (later, Marc's OK).

## Backups
GitHub secrets `BACKUP_DATABASE_URL` (Canner DB external URL, read-only if possible) and
`BACKUP_PASSPHRASE`; copy `docs/ops/nightly-db-backup.yml.example` to `.github/workflows/`.
Note: repo is public — Actions minutes are free; encrypted artifacts only.
