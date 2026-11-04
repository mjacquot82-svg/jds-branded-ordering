# Beta fixes: first-order pay at pickup, shop subdomains, slug stability

Three findings from the beta shop test (Nov 2026).

## A. Pay at pickup on a customer's first order

- Root cause: `pay_at_pickup_min_completed_orders` defaulted to **1**, and guests were blocked in both
  the API (`/payments/pay-at-pickup/*` required a signed-in customer) and the cart UI.
- New default is **0**. Signed-in customers need a verified email; guests need a name plus a phone or
  email. The per-order max total ($25 default) stays as the abuse guard, and No-show marking still
  blocks a customer or a guest's email/phone at that shop.
- Owners keep both settings in **Order settings** and can raise the minimum to send guests back to card.
- Migration `20261103_39` moves rows still at the old value 1 to 0. The table has no "owner changed it"
  marker, so a shop that deliberately saved 1 cannot be told apart; every shop today is a beta shop,
  and any other value (0, 2+) is left alone.

## B. `<slug>.order.jdsstudio.ca` said "Storefront unavailable"

- Root cause, two parts:
  1. Canner's edge in front of `jds-beta-api` rewrites `X-Forwarded-Host` to the API's own hostname, so
     the proxy's forwarded shop host never reached the API.
  2. Even with the right host, the tenant resolver only accepted a **manually verified**
     `storefront_hostnames` row, so a new shop had no mapping and got `tenant_not_found`.
- Fix:
  - `scripts/canner-pilot-server.mjs` also sends `X-JDS-Storefront-Host` (the incoming shop host) and
    `X-JDS-Proxy-Secret`, and strips any client-supplied copies of both.
  - The API trusts `X-JDS-Storefront-Host` only when `JDS_STOREFRONT_PROXY_SECRET` is set and the
    header matches (constant-time), then accepts only a host exactly one label under
    `JDS_STOREFRONT_BASE_DOMAIN`. `JDS_TRUST_PROXY_STOREFRONT_HOST` still works as before.
  - `resolve_storefront_context` now falls back to `<slug>.<base>` for any shop with that slug that is
    live and passes readiness, so no per-shop verification or admin action is needed.

### Canner env changes (both projects, then redeploy)

`jds-pilot-web` / beta web project:

| Variable | Value |
| --- | --- |
| `JDS_STOREFRONT_PROXY_SECRET` | one long random string (e.g. `openssl rand -hex 32`) |

`jds-beta-api`:

| Variable | Value |
| --- | --- |
| `JDS_STOREFRONT_BASE_DOMAIN` | `order.jdsstudio.ca` (already set) |
| `JDS_TRUST_PROXY_STOREFRONT_HOST` | `true` (already set; keep for the older path) |
| `JDS_STOREFRONT_PROXY_SECRET` | **the same** random string |

DNS/TLS: `*.order.jdsstudio.ca` -> web project (already done).

## C. Re-saving the address stripped hyphens

- Root cause: the address field slugified on every keystroke, which deletes a `-` as soon as it is
  typed, so `zz-test-cafe-grok-qa` collapsed to `zztestcafegrokqa` and saving persisted it.
- Fix: typing keeps a trailing hyphen and the value is finalized once on save. Saving a **live** shop's
  address now needs an explicit confirmation (`confirm_live_change`), and saving an unchanged address is
  a no-op.
