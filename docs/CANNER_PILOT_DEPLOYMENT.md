# Controlled DEMO pilot on Canner — setup sheet

Alternative host for the isolated pilot described in
[`CONTROLLED_DEMO_PILOT_DEPLOYMENT.md`](CONTROLLED_DEMO_PILOT_DEPLOYMENT.md).
Same rules apply: new, empty resources only; nothing copied from Guest House,
Ladel's or production; manual deploys; invite-only; noindex.

Canner docs referenced: <https://canner.ca/docs> (quickstart, python, node, vite,
deploys, databases, env-vars, object-storage, plans-limits, troubleshooting) and
<https://canner.ca/pricing>.

## Architecture: two projects, one browser origin

| Project | Runtime | Purpose |
| --- | --- | --- |
| `jds-pilot-api` | Python (root `backend`) | FastAPI API + pilot Postgres + persistent media dir |
| `jds-pilot-web` | Node (repo root) | `scripts/canner-pilot-server.mjs`: serves `dist/`, proxies `/api/*` and `/health/*` to the API |

The owner/customer session is a host-only `__Host-` cookie and writes need the
`X-CSRF-Token` header plus an `Origin` equal to `FRONTEND_URL`. The browser must
therefore talk to a single origin (`https://<web>.canner.app`). Canner's static
Vite hosting has SPA fallback and `_headers` but no documented proxy/redirect
support, so the web project runs a tiny Node server that forwards the same paths
the Netlify pilot proxies (`/api/*`, `/health/*`). `/robots.txt` is served by the
web server itself as `Disallow: /` (the API's robots says `Allow` when staging
review is off).

Proxy safety (see `tests/frontend/cannerPilotServer.test.js`):

- `PILOT_API_ORIGIN` must be a bare `https://` origin on a single-label
  `*.canner.app` host, or exactly `PILOT_API_ALLOWED_HOST`; the server refuses to
  start otherwise. Only `/api/` and `/health/` prefixes are forwarded, always to
  that one origin (no open proxy; protocol-relative and absolute-form targets are
  refused).
- Encoded or literal `..`/`.` segments, backslashes and NUL are rejected with 400
  before routing; static files are resolved strictly inside `dist/`.
- `Origin`, `Cookie`, `X-CSRF-Token` and every `Set-Cookie` pass through unchanged;
  client-supplied `X-Forwarded-*`/`Forwarded` are dropped and replaced with the
  real `Host` and proto. Bodies are streamed (10 MB uploads), no buffering.
- Every response carries `X-Robots-Tag: noindex, nofollow`.

## 1. Supabase (pilot sign-in only)

The backend's providers are `supabase`, `development` (locked to
`JDS_ENVIRONMENT=development` + loopback) and `staging-review` (synthetic Guest
House seed). Real signup + verification email therefore needs a **new** Supabase
project. Canner Auth is passkey-only and is not wired into this app.

1. Create a new Supabase project (free). Do not reuse Guest House/Ladel's/prod.
2. Copy URL, publishable key and secret key for the API env vars below.
3. Auth → URL configuration: Site URL `https://<web>.canner.app`, redirect
   `https://<web>.canner.app/build/verify` (fill in after the web project exists).
4. Check Supabase's built-in email rate limit is enough for 5–10 invitees.

## 2. Canner project `jds-pilot-api`

- Source: GitHub `mjacquot82-svg/jds-branded-ordering`, production branch
  `m2.5/controlled-demo-launch`. **Root directory: `backend`.**
- **Pull-request previews: OFF** (previews share the production database).
- Database tab: provision Postgres 17 (`DATABASE_URL` is injected).
- Settings → Build:
  - Release command: `.venv/bin/python -m app.db.migrate` (runs before each production
    deploy, never on previews).
  - Start command:
    `mkdir -p "$CANNER_DATA_DIR/media" && JDS_LOCAL_MEDIA_ROOT="$CANNER_DATA_DIR/media" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $PORT`
  - Health check path (Settings → Build → Health check path): `/health/ready`.
    Any response under 500 counts as up.
- Consider turning auto-rollback off if a future migration is not backward compatible.

Python: Canner runs Python 3.12.3 (confirmed by Canner, Nov 2). `requires-python`
(`>=3.11,<3.13`) is unchanged and covers it. Canner builds the `pyproject.toml`
into `.venv`; run migrations and the server through `.venv/bin/python`.

### API environment variables (mark secrets sensitive, scope runtime-only where possible)

```text
# DATABASE_URL                    injected by Canner
FRONTEND_URL=https://<web>.canner.app
PUBLIC_APP_URL=https://<api>.canner.app
JDS_ENVIRONMENT=staging
JDS_AUTH_PROVIDER=supabase
JDS_AUTH_SESSION_PEPPER=<new random, >= 32 chars>
JDS_AUTH_SECURE_COOKIES=true
JDS_APPLICATION_KEY=jds-commerce
JDS_STOREFRONT_SCHEME=https
JDS_PAYMENT_MODE=review
JDS_OUTBOUND_INTEGRATIONS_ENABLED=false
JDS_BILLING_ENFORCEMENT_ENABLED=false
JDS_STANDARD_PLAN_MONTHLY_CAD=150
JDS_DEMO_INVITE_CODE=<share only with invitees>
JDS_MEDIA_STORAGE=local
SUPABASE_AUTH_URL=<pilot Supabase URL>
SUPABASE_AUTH_PUBLISHABLE_KEY=<pilot publishable key>
SUPABASE_AUTH_SECRET_KEY=<pilot secret key>
```

Never set: `JDS_ENABLE_STAGING_REVIEW`, Clover tokens, any production
`DATABASE_URL`, production Supabase keys or media bucket.

### Media on `CANNER_DATA_DIR`

`JDS_MEDIA_STORAGE=local` is allowed because the pilot runs as `staging`
(production refuses it). `CANNER_DATA_DIR` is confirmed available on Live (Canner,
Nov 2): it survives deploys, is per-app, is backed up nightly for production
deploys only, and counts against the organization storage pool; preview deploys do not
get it. Backups live on the same server unless off-site copies are configured.
Canner object storage (MinIO, S3-compatible) would need a new storage adapter and
is out of scope for the pilot.

## 3. Canner project `jds-pilot-web`

- Same repo and branch, **root directory `/`**, previews **OFF**.
- **Required: set Framework = Node.js** in Canner. Otherwise Canner deploys it as a
  static site, only `dist/` ships and the proxy never runs (this is what caused the
  Oct 28 revert of `jds-beta-web`).
- Build command: `npm run build` (not `build:staging`, which only accepts Render origins).
- Start command: `node scripts/canner-pilot-server.mjs`
- Health check: `/` (serves `index.html`).
- Env vars:

```text
PILOT_API_ORIGIN=https://<api>.canner.app
# PILOT_API_ALLOWED_HOST=<api custom domain>   only if the API uses a custom domain
```

Do not put secrets in `VITE_*` variables.

## 4. Deploy order

1. Deploy `jds-pilot-api`; confirm `https://<api>.canner.app/health/ready` is 200.
2. Deploy `jds-pilot-web`; confirm `https://<web>.canner.app/health/ready` is 200
   through the proxy and `curl -I https://<web>.canner.app/` shows `X-Robots-Tag`.
3. Set the Supabase redirect URL to the real web host.

## 5. Platform admin grant for Marc

Sign up once at `https://<web>.canner.app/build?invite=<code>` and verify the
email, then run against the pilot database (Database tab / Data Workshop, or psql
with temporary IP-allowlisted external access). Columns and constraint match
migration `20260823_26_add_v1_platform_foundation` (`id` has no server default).

```sql
INSERT INTO platform_grants (id, user_id, capability, is_active, granted_by_user_id, created_at)
SELECT gen_random_uuid(), u.id, c.capability, true, NULL, now()
FROM jds_users u
CROSS JOIN (VALUES ('platform.organizations.read'), ('platform.organizations.write')) AS c(capability)
WHERE lower(u.primary_email) = lower('<marc-email>')
ON CONFLICT ON CONSTRAINT uq_platform_grants_user_capability DO UPDATE SET is_active = true;

SELECT g.capability, g.is_active
FROM platform_grants g JOIN jds_users u ON u.id = g.user_id
WHERE lower(u.primary_email) = lower('<marc-email>');
```

Expect two rows, both `true`. Zero rows inserted means the email didn't match.

## 6. Smoke test

- [ ] `/build?invite=<code>` signup → verification email → `/build/verify` works
- [ ] Harbor & Hearth starter store loads; Design Studio save persists
- [ ] Starter images; upload, replace and delete own photo
- [ ] Redeploy API, uploaded photo still loads (CANNER_DATA_DIR persistence)
- [ ] Two tabs open, save from both (no 403)
- [ ] Owner login and saves pass the CSRF/Origin checks end to end through the
      proxy (Canner's API edge may overwrite `X-Forwarded-Host`)
- [ ] Sign out / in, data persists; preview shows checkout off
- [ ] Activation request appears in `/admin`; Promote to live works
- [ ] Second prospect cannot see or edit the first prospect's data
- [ ] `/robots.txt` is `Disallow: /`; responses carry `X-Robots-Tag: noindex, nofollow`
- [ ] Cold start after sleep: first request wakes both projects (~1–2 s each)
- [ ] Guest House and Ladel's unaffected

## 7. Plan and cost (CAD, plus tax)

- Marc's 3 always-on slots are already used by existing apps. **Decision: both
  pilot projects sleep** after 3 h idle (no extra cost; each wakes in about
  1–2 s, and both may be cold on the first request).
- Always-on would cost $4/mo per project ($8/mo for both) if needed later, e.g.
  before inviting outside testers.

## 8. Canner answers (Colin, Nov 2)

1. `pyproject.toml`-only backend builds fine; Python 3.12.3.
2. Vite + custom start runs as a Node server only with Framework = Node.js.
3. `CANNER_DATA_DIR` available on Live, survives deploys, nightly backups (production deploys).
4. Edge passes `Set-Cookie`/`Origin` and large uploads; it may overwrite
   `X-Forwarded-Host` (covered by the smoke test).
5. Projects can reach each other over their public `https://<app>.canner.app` URLs.
6. Sleeping apps wake in about 1–2 s.
7. All always-on slots are in use (see section 7).
