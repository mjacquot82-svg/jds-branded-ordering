# Beta shop addresses, owner verification email, and console noise

Found in the Nov 3, 2026 beta QA run (test shop `zz-test-cafe-grok-qa`).

## 1. Shop address `<slug>.order.jdsstudio.ca` does not load

**Cause (infrastructure):** `order.jdsstudio.ca` and every `*.order.jdsstudio.ca` name return
NXDOMAIN from the jdsstudio.ca nameservers (GoDaddy, `ns15.domaincontrol.com`). Nothing is
pointed at Canner, so there is no DNS record and no TLS certificate for shop subdomains.

A second, code-side gap: the Canner web project proxies `/api` to the API project, so the API
saw `jds-beta-api.canner.app` as Host and could not tell which shop subdomain was asked for.

### What the code now does
- **Working fallback link everywhere** (`JDS_PILOT_SHOP_LINKS=true`, non-production): the setup
  wizard, launch kit, QR code and printable poster all show
  `https://jds-beta-web.canner.app/?shop=<slug>` instead of the dead subdomain.
- A shop link for a shop that is not live yet shows an "Opening soon" page instead of
  "Storefront unavailable", so a newcomer never lands on a dead link right after sign-up.
  After activation (promote to live + public readiness) the same link opens the storefront.
- **Subdomains ready for when DNS exists:** with `JDS_TRUST_PROXY_STOREFRONT_HOST=true` the API
  resolves the shop from the proxy's `X-Forwarded-Host` when it is exactly one label under
  `JDS_STOREFRONT_BASE_DOMAIN`. It still needs a *verified* hostname mapping and a public-ready
  shop, so it only exposes storefronts that are public anyway.

### Steps for real `<slug>.order.jdsstudio.ca` addresses (not done; Marc to do)
Canner supports wildcard domains (paid/Live plan; added Oct 26, 2026 — docs: https://canner.ca/docs/custom-domains).

1. Canner dashboard → project **jds-beta-web** → Domains → Add domain → `*.order.jdsstudio.ca`.
   The dashboard shows two CNAME records, including a project-specific `_acme-challenge` token.
2. GoDaddy → jdsstudio.ca → DNS → add (copy the token from step 1):
   ```
   Type   Name                   Value                                TTL
   CNAME  *.order                jds-beta-web.canner.app              1 hour
   CNAME  _acme-challenge.order  <token-from-canner>.acme.canner.app  1 hour
   ```
   Do not add anything for `order` itself unless you want `order.jdsstudio.ca` to load too
   (that would be a separate domain in Canner). Do not touch the existing apex/www records.
3. Back in Canner click **Verify** (it also re-checks hourly). Wait for the wildcard certificate.
4. Canner → **jds-beta-api** → Variables:
   ```
   JDS_STOREFRONT_BASE_DOMAIN=order.jdsstudio.ca
   JDS_TRUST_PROXY_STOREFRONT_HOST=true
   ```
   Redeploy jds-beta-api.
5. For each activated shop, verify its hostname in Platform admin (storefront hostname → Verify).
6. Check: `curl -sI https://<slug>.order.jdsstudio.ca/` returns 200 and the storefront loads.
7. Only after that works for every live shop, set `JDS_PILOT_SHOP_LINKS=false` on jds-beta-api so
   the wizard and launch kit switch back to the subdomain address. Until then keep it `true`.

## 2. Owner verification email says "start ordering ahead"

**Cause:** the wording is not in this repo. Sign-up mail is Supabase's **Confirm signup**
template (project `eeqlrsdwivdypdnynofx`), which customers and café owners share. Changing
it to owner wording alone would break the customer email.

**Code change:** owner sign-ups now set Supabase user metadata `signup_flow=owner`
(customers get `signup_flow=customer`), so the template can branch.

**Steps (Supabase dashboard → project eeqlrsdwivdypdnynofx → Authentication → Emails → Confirm signup):**

Subject:
```
{{ if eq .Data.signup_flow "owner" }}Confirm your email to build your JDS ordering app{{ else }}Confirm your email{{ end }}
```
Body (HTML):
```html
{{ if eq .Data.signup_flow "owner" }}
<h2>Confirm your email</h2>
<p>Thanks for starting your café's ordering app with JDS Studio.</p>
<p>Please confirm your email address so you can finish setting up your menu, branding and hours.</p>
<p><a href="{{ .ConfirmationURL }}">Confirm my email and continue setup</a></p>
<p>If you didn't sign up, you can ignore this email.</p>
{{ else }}
<!-- keep the existing customer body here, unchanged -->
{{ end }}
```
Paste the current customer body into the `else` branch so customers see no change. Save.
Accounts created before this deploy have no `signup_flow`, so they keep getting the customer text.

## 3. Console errors on /setup/* pages

**Cause:** every page load fetched `/api/v1/storefront/bootstrap` and
`/api/v1/customer/auth/session`. On the platform host there is no storefront, so both
answered 404 and Chrome logged "Failed to load resource" twice per page (plus once more on
navigation — the 3 errors seen). Harmless, but noisy and confusing.

**Fix:** operations pages (`/admin /owner /staff /build /activate /setup /go-live`) call
bootstrap with `optional=1`, which answers 204 when no storefront matches; the shopper
session is not requested on operations pages at all.
