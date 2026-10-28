# jds-branded-ordering

Processor-neutral multi-tenant branded ordering for coffee shops and cafés.
Merchants own their payment processor account; JDS is not the merchant of record.

Clover is supported as the first working payment adapter. The platform itself
must not require Clover for a tenant to exist or operate (see
`docs/M1_PAYMENT_PROVIDER_ABSTRACTION.md`).

## Docs

| Doc | Purpose |
| --- | --- |
| `.env.example` | Annotated env template (required/optional, Clover vs provider-neutral) |
| `docs/PRODUCTION_DEPLOYMENT.md` | Production Render / Netlify / Supabase runbook |
| `docs/STAGING_REVIEW_DEPLOYMENT.md` | Synthetic staging-review package (never inherits prod) |
| `docs/MERCHANT_HOSTNAME_PROVISIONING.md` | Hostname / `public_ready` ops + hosted auto-verify |
| `docs/M1_PAYMENT_PROVIDER_ABSTRACTION.md` | **Design only** — payment port / adapter boundary |
| `docs/CLOVER_ADAPTER_RUNBOOK.md` | Optional Clover adapter ops (not a platform prerequisite) |
| `docs/WEB_PUSH_RELEASE.md` | Web push release notes |
| `docs/STARTER_PRODUCT_MEDIA.md` | Starter media pack |
| `backend/README.md` | Backend phase notes, auth, media |

## Local tests (backend)

```bash
cd backend
export TEST_DATABASE_URL="postgresql+psycopg://guesthouse:password@127.0.0.1:5432/guesthouse_test"
. .venv/bin/activate
pytest
```

Migration tests reset the shared test schema so intentional V1 downgrade
data-loss guards are not tripped by leftover multi-tenant fixtures from other
suites.
