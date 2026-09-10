# Clover adapter runbook (optional payment provider)

Clover is the **first working payment adapter**, not a platform prerequisite.
Tenants without Clover remain valid organizations. See
`docs/M1_PAYMENT_PROVIDER_ABSTRACTION.md` for the processor-neutral target.

## When to configure

Only when you intend to offer Clover Hosted Checkout to merchants who already
(or will) process on Clover.

## Required secrets (API service)

See `.env.example` section **Clover payment adapter**:

- `CLOVER_APP_ID`, `CLOVER_APP_SECRET`
- `CLOVER_TOKEN_ENCRYPTION_KEY` (Fernet)
- `CLOVER_STATE_SECRET`, `CLOVER_WEBHOOK_SECRET` (≥32 chars, distinct)
- `CLOVER_ENVIRONMENT` = `sandbox` | `production`
- `PUBLIC_APP_URL`, `FRONTEND_URL` for OAuth/return URLs

Optional: `CLOVER_PAGE_CONFIG_UUID`. Do not use legacy
`CLOVER_ECOMMERCE_PRIVATE_TOKEN` in multi-tenant OAuth mode.

## Merchant connect

1. Owner opens Payments / Clover connect in admin.
2. OAuth: `GET /api/v1/clover/oauth/start` → callback stores encrypted tokens on
   `clover_installations` scoped to `organization_id`.
3. Checkout: storefront creates pending order, then
   `POST /api/v1/clover/.../hosted-checkout` (exact path per `clover.py`).
4. Webhooks: `POST /api/v1/clover/webhooks/hosted-checkout`.

## Staging

Staging review **refuses** real Clover credentials by design
(`docs/STAGING_REVIEW_DEPLOYMENT.md`). Use sandbox only on a non-staging
dedicated environment when proving checkout.

## Non-goals

- Do not make Clover required for hostname or org provisioning.
- Do not implement Stripe/Square/Moneris here.
- Do not put Clover secrets in Netlify `VITE_*` variables.
