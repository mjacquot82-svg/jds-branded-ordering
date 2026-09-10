# Controlled demo pilot deployment (M2.5)

**Purpose:** Private end-to-end browser test for Marc + ~5–10 invitees of the
self-service “Build Your Store Free” funnel.

**Hard rules**

- NOT production
- NOT Guest House / Ladel's / any existing customer environment
- Do NOT clone production env groups or restore production data
- Do NOT announce publicly or run ads
- Do NOT enable automated C$150 billing
- Prefer invite code (`JDS_DEMO_INVITE_CODE`) over open signup
- `autoDeploy: false` until Marc explicitly approves a deploy

## Verdict default for agents

If DNS, secrets, Supabase project, or new paid Render/Netlify resources are
required: **prepare this package and stop**. Do not spend money or touch
customer envs. Marc completes the checklist below.

## Target shape (dedicated pilot stack)

| Layer | Target | Notes |
| --- | --- | --- |
| Frontend | Dedicated Netlify site | Use `netlify.pilot.toml`; `X-Robots-Tag: noindex` |
| Backend | Dedicated Render web service | Mirror `render.pilot.yaml`; `autoDeploy: false` |
| Database | Dedicated Render PostgreSQL | Empty DB; migrate only; **no** production dump |
| Media | Local disk on Render **or** dedicated Supabase private bucket | Never Guest House bucket |
| Auth | Dedicated Supabase Auth project (or isolated project) | Email verification templates → `/build/verify` |
| Hostname | Netlify generated HTTPS hostname first | Custom domain optional later |

Suggested names (examples only — Marc chooses in dashboards):

- Netlify site: `jds-demo-pilot`
- Render API: `jds-branded-ordering-demo-pilot-api`
- Render DB: `jds-branded-ordering-demo-pilot-db`

## Expected recurring cost (order-of-magnitude, CAD)

Report before creating paid resources:

| Resource | Typical starter cost | Notes |
| --- | --- | --- |
| Render web (starter) | ~US$7/mo | Or free tier if available; confirm current pricing |
| Render PostgreSQL | ~US$6–7/mo | Dedicated; do not share staging-review DB if it holds other data you care about isolating |
| Netlify site | Usually $0 on starter for low traffic | Confirm plan limits |
| Supabase Auth + DB optional storage | Often $0 on free tier for pilot traffic | New project; never reuse customer project |
| CAPTCHA (optional) | Cloudflare Turnstile free tier common | Only if Marc creates vendor account |
| **Total ballpark** | **~$0–20 USD/mo** if reusing unused free tiers; **~$15–25 USD/mo** if new paid Render pair | Agents must STOP and confirm with Marc before creating paid infra |

This pilot must not create permanently free live ecommerce or bill merchants.

## Required environment variables (pilot)

### Netlify

```text
JDS_STAGING_API_ORIGIN=<https://pilot-api-host>   # build-time proxy target (same pattern as staging)
NETLIFY_CONFIG_PATH=netlify.pilot.toml
```

Do **not** set secrets in `VITE_*` variables.

### Render API

Reuse the staging-review variable *names* where sensible, with pilot values:

```text
DATABASE_URL=<pilot DB>
FRONTEND_URL=<pilot Netlify URL>
PUBLIC_APP_URL=<pilot Netlify URL>
JDS_ENVIRONMENT=staging
JDS_AUTH_PROVIDER=supabase
JDS_AUTH_SESSION_PEPPER=<new random >=32>
JDS_AUTH_SECURE_COOKIES=true
JDS_APPLICATION_KEY=jds-commerce
JDS_STOREFRONT_SCHEME=https
JDS_PAYMENT_MODE=review
JDS_OUTBOUND_INTEGRATIONS_ENABLED=false
JDS_BILLING_ENFORCEMENT_ENABLED=false
JDS_STANDARD_PLAN_MONTHLY_CAD=150
JDS_DEMO_INVITE_CODE=<share only with invitees>
JDS_LOCAL_MEDIA_ROOT=/var/data/jds-demo-pilot-media   # if using disk
# OR supabase media vars pointing at a NEW private bucket
SUPABASE_AUTH_* / identity provider keys for the pilot project
```

Explicitly **unset / never copy** from customer production:

- Guest House / Ladel's Clover tokens
- Production `DATABASE_URL`
- Production Supabase service role
- Production media bucket

Do **not** set `JDS_ENABLE_STAGING_REVIEW=true` on the pilot unless you intentionally want the synthetic Guest House review seed — for M2.5 demo funnel testing, leave staging-review **off** so Harbor & Hearth self-service signup is the path under test.

## Migrations

```bash
python -m app.db.migrate
```

Head includes M2 revision `20260910_33` (commercial_mode, demo tables). No destructive migration in M2.5.

## Marc step-by-step (when new infra is needed)

1. Confirm expected cost above is acceptable.
2. Create a **new** Supabase project for pilot Auth (and optional storage).
3. Create a **new** Render PostgreSQL + web service from `render.pilot.yaml` (manual approve; autoDeploy false).
4. Set Render env vars; run migrate via pre-deploy.
5. Create a **new** Netlify site; set config path to `netlify.pilot.toml`; set `JDS_STAGING_API_ORIGIN` to the Render URL; deploy branch `m2.5/controlled-demo-launch` (or merged foundation later — not automatic).
6. Set `JDS_DEMO_INVITE_CODE` and share `https://<pilot>/build?invite=<code>` with 5–10 people only.
7. Configure Supabase email template redirect to `https://<pilot>/build/verify`.
8. Bootstrap platform grant for Marc’s owner user so `/admin` platform prospects/activations are visible.
9. Smoke: signup → verify → Design Studio → preview (checkout off) → activation request → appears in platform admin.
10. Confirm robots noindex and that Guest House / Ladel's URLs are untouched.

## If an isolated existing staging stack can be reused

Only reuse when **all** are true:

- Dedicated DB/media (no customer data)
- No production credentials
- Marc explicitly approves reuse
- Invite code set; URL not announced

Still do **not** expose broadly.

## Isolation checklist

- [ ] Pilot DB ≠ production DB
- [ ] Pilot media ≠ Guest House / Ladel's media
- [ ] Pilot Supabase ≠ customer Supabase
- [ ] Clover outbound disabled or unused
- [ ] `robots` / `X-Robots-Tag: noindex`
- [ ] Invite code required
- [ ] Prospect commerce lockouts verified on the deployed URL

## Marc admin usage (prospects + funnel)

1. Sign in as platform-grant holder on the pilot URL.
2. Open Platform Admin.
3. **Demo prospects** — list of `commercial_mode=prospect` orgs, activation summary, recent funnel events (`demo_started`, `logo_added`, …).
4. **Activation requests** — leads with business, email, processor preference, status.
5. **Promote to live** — flips commercial mode; preserves design/catalog/media; does **not** charge C$150 automatically.
