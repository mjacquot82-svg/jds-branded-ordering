# Merchant hostname provisioning

## Problem (current)

Public storefront readiness (`evaluate_storefront_readiness`) requires exactly
one **verified + canonical** `storefront_hostnames` row per organization.

Merchant flow:

1. Owner chooses a slug via `PUT /api/v1/owner/storefront`.
2. API builds `{slug}.{JDS_STOREFRONT_BASE_DOMAIN}` when that env is set.
3. Historically the row was created as `status=pending`, `is_canonical=false`.
4. The only promotion path was `POST /api/v1/platform/admin/hostnames/{id}/verify`,
   which requires a `platform.organizations.write` platform grant.

Effects:

- Merchants cannot reach `public_ready` without a JDS operator round-trip.
- If `JDS_STOREFRONT_BASE_DOMAIN` is unset, choose-storefront returns HTTP 503.
- DNS/TLS for the hosted base domain is an infrastructure concern (wildcard
  certificate + Netlify/CDN), separate from the DB verification flag.
- Readiness also still gates on a connected Clover installation today; that is a
  **payment-port** issue tracked for M1 design (processor-neutral), not hostname DNS.

This is provider-neutral: hostnames are tenancy/routing, not Clover.

## M0 small fix (implemented)

For hostnames that exactly match the configured hosted pattern
`{slug}.{JDS_STOREFRONT_BASE_DOMAIN}`, `choose_storefront` now:

- marks the row `verified` + `canonical`
- clears canonical on other hostnames for that tenant
- synchronizes onboarding/`public_ready`

Rationale: JDS owns DNS/TLS for the hosted base domain, so a separate admin
“verify DNS” step is redundant for those names and only created operational
friction. Audit action: `storefront.hostname_auto_verified`.

Custom domains (future) and non-hosted names still require the platform admin
verify endpoint (or a future automated DNS challenge).

## Recommended design (do not overbuild in M0)

| Hostname class | Who owns DNS | Verification |
| --- | --- | --- |
| `{slug}.{JDS_STOREFRONT_BASE_DOMAIN}` | JDS | Auto on choose (M0) |
| Custom apex/www | Merchant | ACME/DNS TXT challenge + async worker; platform admin override remains |
| Staging review hosts | JDS synthetic | Seeded / review cookie; never production DNS |

Infrastructure decisions still needed before custom domains:

1. Wildcard cert strategy on Netlify (or alternate edge) for the hosted base.
2. Whether custom domains terminate on the same SPA origin with Host header
   routing (preferred; matches `StorefrontHostname` resolution) vs per-tenant
   sites.
3. Rate limits / slug policy / reserved names.
4. Decoupling readiness `clover` check into a generic `payment_provider_connected`
   check (M1 payment abstraction — design only in M0).

## Ops checklist

1. Set `JDS_STOREFRONT_BASE_DOMAIN` in production API env.
2. Ensure wildcard DNS + HTTPS for that base on the SPA edge.
3. Confirm merchant choose-storefront returns `status=verified`.
4. Keep platform admin verify for exceptions and future custom domains.
