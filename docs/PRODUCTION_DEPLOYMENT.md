# Production deployment runbook (Render + Netlify + Supabase)

Processor-neutral multi-tenant SaaS. Clover may be enabled as the first payment
adapter for merchants who use Clover; it must **not** be required for the
platform itself to exist. Do not copy staging credentials. No production deploy
is performed by M0 hygiene work.

## Preconditions

1. Dedicated Supabase project (Auth + private Storage bucket).
2. Dedicated Render web service + PostgreSQL (not the staging-review pair).
3. Dedicated Netlify site for the storefront/owner SPA.
4. DNS for `JDS_STOREFRONT_BASE_DOMAIN` (wildcard `*.order.jdsstudio.ca` or
   chosen base) pointing at the Netlify site / CDN with HTTPS.
5. Secrets stored only in Render / Netlify / password manager — never in git.

## Backend (Render)

Suggested shape (mirror `render.staging.yaml` with production names):

- `rootDir: backend`
- `buildCommand: pip install .`
- `preDeployCommand: python -m app.db.migrate`
- `startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- `healthCheckPath: /health/ready`
- `autoDeploy: false` until M0/M1 are signed off

Required production env groups (see root `.env.example` for full annotated list):

| Group | Required vars | Notes |
| --- | --- | --- |
| Core | `DATABASE_URL`, `FRONTEND_URL`, `PUBLIC_APP_URL`, `JDS_ENVIRONMENT=production` | Provider-neutral |
| Auth | `SUPABASE_AUTH_*`, `JDS_AUTH_SESSION_PEPPER`, `JDS_AUTH_SECURE_COOKIES=true`, `JDS_APPLICATION_KEY` | Provider-neutral identity |
| Media | `JDS_MEDIA_STORAGE=supabase`, `JDS_SUPABASE_STORAGE_*` | Private bucket; service role server-only |
| Hostnames | `JDS_STOREFRONT_BASE_DOMAIN`, `JDS_STOREFRONT_SCHEME=https` | Enables merchant self-serve hosted subdomains |
| Clover (optional adapter) | `CLOVER_*` | **Clover-specific**; only needed when offering Clover checkout |
| Push (optional) | `WEB_PUSH_*`, `PUSH_*` | Provider-neutral |

After first migrate, provision foundation deliberately:

```bash
python -m app.jds_auth.bootstrap_owner \
  --email owner@example.com \
  --application-name "JDS Commerce" \
  --organization-name "First Merchant"
```

## Frontend (Netlify)

- Use `netlify.toml` (production). Staging uses `netlify.staging.toml` only.
- Prefer same-origin `/api` proxy to Render; leave `VITE_API_BASE_URL` empty
  unless a deliberate split origin is required.
- Never put Supabase secret, Clover secrets, or DB URLs in `VITE_*` vars.

## Clover adapter (optional per merchant)

1. Configure platform Clover app credentials on the API service.
2. Merchant connects via owner OAuth (`/api/v1/clover/...`).
3. Tokens stay encrypted at rest (`CLOVER_TOKEN_ENCRYPTION_KEY`).
4. Merchants without Clover are still valid tenants; payment readiness for
   non-Clover processors is an M1 boundary (design) / later adapter work.

## Hostname activation

See `docs/MERCHANT_HOSTNAME_PROVISIONING.md`. Hosted subdomains under
`JDS_STOREFRONT_BASE_DOMAIN` auto-verify on merchant choice. Custom domains
remain a platform-admin / infrastructure decision.

## Verification checklist

- [ ] `GET /health/live` and `GET /health/ready` succeed
- [ ] Migrations at head (`20260903_31` or later)
- [ ] Owner invite/login works against Supabase Auth
- [ ] Media upload round-trip through private bucket
- [ ] Hosted subdomain resolves storefront for a test tenant
- [ ] Clover sandbox checkout only if that adapter is in scope for the merchant
- [ ] No staging/review flags (`JDS_ENABLE_STAGING_REVIEW`, local review) set

## Explicit non-goals of this runbook

- JDS subscription / MoR billing implementation
- Stripe / Square / Moneris adapters
- Automatic production deploy from M0 PRs
