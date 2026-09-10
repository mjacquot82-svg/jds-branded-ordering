# Grok Coffee SaaS Market-Readiness Audit — JDS Branded Ordering

**Audited repository:** https://github.com/mjacquot82-svg/jds-branded-ordering  
**Primary analysis tip:** `feature-production-image-foundation` @ `be56dab71beef72cd9c2a5c7008bd328e186a849`  
**Audit branch:** `audit/market-readiness-20260910`  
**Audit date:** 2026-09-10 (America/Toronto)  
**Auditor:** Grok (box clone; no merge, no production deploy, no architecture rewrite)  
**Business framing:** Multi-tenant branded coffee-shop ordering SaaS (~C$150/mo). JDS sells software only (not merchant of record, no % of sales). Each shop owns its payment processor. Payment must sit behind an abstraction; Clover is optional only. Design Studio is the differentiator. No runtime AI image dependency.

---

## 1 Executive summary

The `feature-production-image-foundation` branch is the most complete product state and is **5 commits ahead of `main`**. It delivers a serious multi-tenant spine (organizations, hostname storefront resolution, tenant-scoped catalog/orders/Clover installations, isolation tests), a design-first merchant setup wizard, Design Studio with draft/publish + live phone preview, product/media foundations, owner operations, launch kit (URL/QR/print), and a fail-closed staging-review package.

Against Marc/JDS market rules, the largest strategic gap is **payment architecture**: checkout, order ledger fields, readiness gates, OAuth, webhooks, and owner UX are **Clover-hardwired**. `src/services/paymentService.js` is still a mock placeholder. There is no provider-neutral payment port. That conflicts with “MUST NOT assume Stripe/Square/Clover/Moneris” and “Clover optional only.”

**Verdict: B — CLOSE (~70%)** for piloting a **first real coffee shop that already uses Clover and is CAD/HST-compatible**, after completing the listed P0/P1 operational items. Multi-processor market readiness is lower until the payment boundary is extracted. Not A: payment coupling, missing production packaging docs, migration-suite regressions on this tip, and incomplete SaaS billing collection block a confident general pilot.

Evidence highlights:
- Frontend tests: **389/389 pass**; Vite production build **succeeds**.
- Backend tests: **323 passed, 20 failed** — all failures in `backend/tests/test_migrations.py` (downgrade/bootstrap). Tenant isolation + media suites rechecked green.
- No ESLint/Prettier/TypeScript scripts exist in `package.json` (lint/typecheck/format N/A).
- No runtime AI image dependency found in app source.

---

## 2 Repo/branch/commit state

| Item | Value |
|---|---|
| Clone path | `/workspace/jds-branded-ordering` |
| Working tree at audit start | Clean clone |
| `origin/main` | `2c39e81f5ad9cf925a2c90d4d25a0894e7d340d4` — *feat: prepare persistent staging review environment* (2026-08-20 UTC) |
| `origin/feature-production-image-foundation` | `be56dab71beef72cd9c2a5c7008bd328e186a849` — *Add production tenant image foundation* (2026-09-03 UTC) |
| Ahead of main | **5 commits, not merged** |
| Branches on origin | `main`, `feature-production-image-foundation` |
| Audit checkout | Local `audit/market-readiness-20260910` tracking feature tip |

**Commits on feature not in main:**
1. `919ed13` feat: add design-first setup wizard and structural layouts  
2. `547a3e4` feat: complete new merchant lifecycle and design studio onboarding  
3. `5d84c67` feat: complete design studio polish and business setup  
4. `463ded0` feat: complete shared catalog manager for merchant setup  
5. `be56dab` Add production tenant image foundation  

**Diff size vs main:** 113 files, +4769 / −401.

**How main differs:** `main` stops at staging-review packaging. Feature adds the merchant lifecycle/setup wizard, Design Studio polish, shared catalog manager for setup, and product↔media asset foundation (`20260903_31` migration). Primary audit uses feature tip; main is an older but still multi-tenant baseline without those five commits.

Known facts from the brief were **verified exact**.

---

## 3 Existing architecture

**Frontend:** React + Vite SPA (`package.json`, `vite.config.js`), Netlify publish (`netlify.toml` / `netlify.staging.toml`). Customer storefront pages under `src/pages/`; owner/admin under `src/admin/`; design system under `src/design/`; setup wizard `src/setup/SetupWizard.jsx`. Tenant browser isolation helpers in `src/services/tenantBrowserState.js` / `src/tenant/TenantContext.jsx`.

**Backend:** FastAPI app `backend/app/main.py` (still titled “The Guest House API”; package name `guesthouse-backend`). Domains: `tenancy/`, `catalog/`, `availability/`, `orders/`, `clover/`, `jds_auth/`, `platform/` (design, media, acquisition, entitlements, readiness), `communications/`, `loyalty/`, `push/`, `customers/`. Alembic migrations under `backend/migrations/versions/` (linear head `20260903_31`).

**Data / identity:** PostgreSQL via SQLAlchemy. Owner auth: Supabase Auth credentials + JDS sessions/memberships (`backend/README.md`). Development/staging identity providers for review modes. Media: `LocalMediaStorage` or private Supabase Storage (`backend/app/platform/media.py`).

**Deploy:** Frontend Netlify; staging API Render + dedicated Postgres + disk (`render.staging.yaml`, `docs/STAGING_REVIEW_DEPLOYMENT.md`). Staging intentionally refuses production Clover/Supabase/VAPID credentials.

**Tenancy model:** Canonical `organizations.id` UUID; `TenantContext` immutable; resolvers by verified hostname, membership, Ladel’s compatibility host, or guarded review modes (`backend/app/tenancy/resolver.py`). Client-supplied tenant headers/query keys fail closed.

---

## 4 What is already complete

- Multi-tenant ownership spines for catalog, availability, orders, auth sessions/staff, Clover installations, platform foundation (design/media/onboarding/hostnames/billing plan tables).
- Explicit automated tenant isolation tests (catalog/orders/Clover/auth/platform) — passing on this tip.
- Design Studio V1: templates `modern` / `minimal` / `cozy`, colors/fonts/buttons, sections, draft save, publish/revert path, phone preview, contrast validation (`backend/app/platform/design.py`, `src/admin/DesignStudioPage.jsx`).
- Design-first setup wizard (welcome → look → brand → business → catalog → ordering → payments → preview → launch) (`src/setup/SetupWizard.jsx`).
- Merchant acquisition/activation lifecycle (`backend/app/platform/acquisition.py`, activation page).
- Storefront readiness gate including catalog, hours, design, clover, hostname (`backend/app/platform/readiness.py`).
- Customer browse/cart/checkout order creation with idempotency (`src/services/checkoutOrder.js`, orders API).
- Clover OAuth + Hosted Checkout + webhook/payment evidence models and API (`backend/app/api/v1/clover.py`, `backend/app/clover/*`).
- Owner ops: products/modifiers/categories, scheduling, orders/fulfillment, customers, communications, loyalty (entitlement-gated), staff PINs, launch kit URL/QR/print.
- Platform admin organization health view (`src/admin/PlatformAdminPage.jsx`).
- Private media pipeline with validation/optimization; product media asset linkage on feature tip; starter product media library (`docs/STARTER_PRODUCT_MEDIA.md`).
- Staging-review fail-closed environment (`JDS_PAYMENT_MODE=fixture-disabled`, disabled Clover routes).
- Local review seed path without contacting Supabase/Clover.
- Large frontend unit/runtime test suite; most backend functional tests green.
- Web push foundation (docs + migrations) as engagement tier capability.

---

## 5 What is partially complete

- **Payment:** Real Clover path exists; provider abstraction does not. Mock `paymentService.js` unused by cart.
- **Billing/SaaS commercial:** `billing_plans` / `organization_subscriptions` / entitlements exist; `JDS_BILLING_ENFORCEMENT_ENABLED` defaults off. No evidence of collecting ~C$150/mo from merchants in-app.
- **Hostname / DNS:** Verified hostname required for public readiness; self-serve DNS automation / custom domains not fully productized for arbitrary shops.
- **Docs packaging:** Staging docs exist; `.env.example`, `docs/CLOVER_INTEGRATION_SETUP.md`, `docs/RENDER_DEPLOYMENT.md` referenced by `backend/README.md` are **missing** from the tree.
- **Branding residue:** Backend still named Guest House / guesthouse; Ladel’s compatibility tenant hard-coded (`LADELS_ORGANIZATION_*` in resolver).
- **Tax/currency:** Configurable per settings in places, but defaults/tests heavily CAD + HST (`orders/constants.py`, `orders/pricing.py`, profile defaults).
- **Fulfillment:** Browser staff/owner fulfillment exists; “use existing Clover hardware without extra devices” not fully generalized beyond checkout integration.
- **Migration hygiene on feature tip:** Upgrade path used by app; full downgrade/bootstrap test suite currently red (see §19).
- **Product spec vs business rules:** `JDS_PRODUCT_SPEC_V2.md` still centers Clover as the V1 payment path (“Connect Clover”), while Marc’s market rules require processor neutrality.

---

## 6 What is missing

- Provider-neutral payment port (authorize/capture/refund/webhook/reconcile) with Clover as one adapter.
- Non-Clover checkout UX and readiness checks (payments step currently “Connect Clover”).
- Documented production env template (`.env.example`) and missing CLOVER/RENDER runbooks referenced in README.
- Per-tenant media storage quotas / plan enforcement.
- Automated merchant DNS / subdomain provisioning UX beyond slug + verified hostname records.
- First-class SaaS subscription checkout for JDS’s ~C$150/mo fee (separate from shop customer payments).
- ESLint / Prettier / TypeScript (or equivalent) CI quality gates — not present.
- Full removal of Guest House / Ladel’s product identity from API titles and package metadata.
- Multiple POS providers, delivery logistics, native apps, AI design — correctly absent (and should stay absent per §29).

---

## 7 Multi-tenant readiness

**Strong.** Organization UUID is canonical; repositories and FKs carry `organization_id`; storefront resolution uses verified hostnames; untrusted tenant headers rejected; browser state keys are host-scoped; isolation tests cover catalog, availability, orders, Clover, auth, and V1 platform surfaces.

Residual risks: Ladel’s compatibility fallback must remain narrowly host-bound (it is); staging/local review modes must never enable in production (guards exist); CDN/cache headers and service worker caching still need production discipline (`public/service-worker.js`). Platform impersonation is limited; audit events exist.

**Status:** Ready enough for multi-shop data isolation; operational hostname provisioning is the practical multi-tenant gap for onboarding volume.

---

## 8 Tenant onboarding readiness

**Mostly ready for guided onboarding.** Acquisition sources include `clover`, `direct`, `invitation`, `platform`, review modes (`acquisition.py`). Activation + design-first wizard + readiness checklist + launch flow are implemented. Payments step and readiness still **require Clover** for `public_ready`, which blocks non-Clover shops from going live even if software is otherwise ready.

Self-serve “create account → Design Studio immediately” is substantially present. Email delivery for activation uses a deferred/no-op default adapter unless wired — production SMTP/Supabase invite templates still operational work.

---

## 9 Storefront readiness

Customer Home/Menu/Cart/Account/Orders/Confirmation routes exist (`src/App.jsx`). Published design drives storefront config via platform API. PWA manifest/icons present. Staging/local review banners and payment-disabled modes work. Public readiness requires organization active, business profile, verified canonical hostname, ordering enabled, 7 hours rows, sellable catalog, published design, **and connected Clover**.

For a branded coffee pilot on a verified host with catalog + design + Clover: **storefront is pilot-capable**.

---

## 10 Coffee menu/model readiness

Catalog supports categories, products, variants, modifier groups/options, quantities, availability/scheduling, lunch special, product images (starter library + uploads + `media_asset_id` on feature tip). Owner catalog manager completed on this branch. Defaults and seeds remain café-oriented (Guest House / CAD). Suitable for coffee-shop menus; not limited exclusively to coffee in schema.

---

## 11 Order-system readiness

Pending order domain with idempotency keys, fingerprints, tax snapshot fields, fulfillment statuses (`new/preparing/ready/completed/cancelled`), owner/kitchen order APIs, customer order views. Checkout creates order then redirects into **Clover Hosted Checkout** (`CartPage.jsx` → `createCloverCheckout`). Order rows embed Clover checkout session columns (`orders/models.py`). Solid for Clover merchants; not processor-agnostic.

---

## 12 Payment architecture

| Layer | Reality |
|---|---|
| Intended abstraction | Missing as a first-class port |
| Frontend cart | Calls `cloverService.createCloverCheckout` only |
| `paymentService.js` | Mock `confirmPayment` returning `pay_mock_*` — not used by cart |
| Backend checkout | `/api/v1/clover/...` Hosted Checkout + OAuth + webhooks |
| Order schema | `clover_*` columns + installation FK |
| Readiness / wizard | Clover connection required |
| Staging | `JDS_PAYMENT_MODE=fixture-disabled` rejects Clover routes |
| JDS SaaS fee billing | Entitlements tables only; not shop-customer payments |

**Conclusion:** Payment is a **Clover integration product**, not yet a multi-tenant payment abstraction. That is the core market-architecture miss relative to JDS business rules.

---

## 13 Complete map of current payment-provider coupling

| FILE/MODULE | CURRENT PROVIDER ASSUMPTION | CORE OR PROVIDER-SPECIFIC | RECOMMENDED BOUNDARY | MIGRATION RISK |
|---|---|---|---|---|
| `src/services/cloverService.js` | Clover Hosted Checkout + connection/OAuth URLs | Provider-specific | Move behind `paymentsApi.startCheckout(orderToken)` adapter | Low–med (rename + interface) |
| `src/services/paymentService.js` | Mock / “Future Stripe/Clover” comment | Placeholder | Become thin client of provider-neutral payment API **or delete** once real port exists | Low |
| `src/services/checkoutOrder.js` | Imports `CloverCheckoutError` | Mixed (order core + Clover errors) | Keep order prep core; map provider errors via payment port | Low |
| `src/pages/CartPage.jsx` | Direct `createCloverCheckout` + Clover UX copy | Provider-specific UX | “Pay securely” → payment port; provider chosen by tenant config | Med |
| `src/pages/ConfirmationPage.jsx` | Clover return assumptions (file in payment grep set) | Provider-specific | Normalize paid/failed via order status API | Med |
| `src/setup/SetupWizard.jsx` (`PaymentSetupStep`) | “Connect Clover” | Provider-specific | “Connect your payment processor” + pluggable connectors | Med |
| `src/admin/OnboardingPage.jsx` | Readiness copy requires Clover | Provider-specific | Readiness key `payments` not `clover` | Med |
| `src/admin/LaunchPage.jsx` / Platform admin Clover columns | Clover health as launch signal | Provider-specific ops | Generic payment health | Low–med |
| `src/admin/OrdersPage.jsx` / owner presentation | May surface Clover payment state | Mixed | Show provider-neutral payment status | Low |
| `backend/app/api/v1/clover.py` | Full Clover OAuth/checkout/webhook/reconcile | Provider-specific | Keep as `adapters/clover`; route webhooks by provider | High (large module) |
| `backend/app/clover/client.py` | Clover HTTP API | Provider-specific | Adapter only | High |
| `backend/app/clover/config.py` | `CLOVER_*` env, merchant id, page config | Provider-specific | Per-tenant installation settings | Med |
| `backend/app/clover/models.py` | `clover_installations`, `clover_payment_events`, OAuth states | Provider-specific tables OK | Keep tables; add `payment_installations` façade or provider enum | High if renamed carelessly |
| `backend/app/clover/security.py` | Clover OAuth state + webhook HMAC | Provider-specific | Adapter security helpers | Med |
| `backend/app/orders/models.py` | `clover_installation_id`, checkout session/url/expiry columns + constraints | **Should be core + provider refs** | `payment_provider`, `payment_installation_id`, `checkout_session_id`, `checkout_url` | **High** (constraints/FKs) |
| `backend/app/platform/readiness.py` | Check key `"clover"` | Provider-specific gate | `"payments"` / provider-connected | Med (product behavior change) |
| `backend/app/platform/acquisition.py` | Acquisition source includes `clover` | OK as channel | Keep clover as acquisition channel, not sole payment | Low |
| `backend/app/main.py` / `staging.py` | `JDS_PAYMENT_MODE`, staging disables Clover | Core flag + Clover coupling | Keep payment mode; disable all providers in staging | Low |
| `backend/app/api/v1/platform.py` | Review `paymentMode`; platform clover health | Mixed | Generic payment health in platform DTO | Low |
| Migrations `20260729_04`, `20260818_20`, `20260822_25` | Clover schema evolution | Provider-specific history | Leave history; additive neutral columns later | High if rewritten |
| Frontend/backend Clover tests | Assert Clover behaviors | Provider-specific | Keep as adapter tests; add port contract tests | Med |
| `JDS_PRODUCT_SPEC_V2.md` | V1 narrative centers Clover | Product docs | Update to “payment adapter; Clover first adapter” | Low |
| `docs/STAGING_REVIEW_DEPLOYMENT.md` | Disables Clover/payment | Appropriate | Keep | n/a |

No Square/Stripe/Moneris live integrations found (Square appears only as **image aspect-ratio** UI copy in Design Studio / product image requirements — not payments).

---

## 14 Recommended provider abstraction

**Do not rewrite commerce.** Add an additive boundary:

1. **Tenant payment installation** record: `organization_id`, `provider` (`clover` initially), `status`, encrypted credentials/refs, environment.
2. **Port** (backend): `create_checkout(order)`, `handle_webhook(provider, headers, body)`, `reconcile(payment_ref)`, `connection_status(org)`.
3. **CloverAdapter** wraps existing `app/clover/*` and `/api/v1/clover/*` (can remain mounted for compatibility).
4. **Neutral routes** e.g. `POST /api/v1/payments/orders/{public_token}/checkout` selecting adapter from tenant installation.
5. **Order columns:** additive nullable `payment_provider` + generic session fields; keep `clover_*` until dual-written then deprecate.
6. **Readiness:** `payments.connected` true if any allowed adapter connected; product policy can still require a provider before launch without naming Clover in UX.
7. **Frontend:** replace direct `cloverService` cart calls with `paymentService` real implementation.
8. Explicitly **defer** Stripe/Square/Moneris adapters until one second merchant demand appears — but the port must exist first so Clover is optional in the architecture.

---

## 15 Design Studio readiness

**Differentiator is real and largely V1-complete on this branch.** Templates, brand controls, image slots (logo/hero/app icon) with crop/position/zoom, live phone preview, draft/publish, diagnostics, setup embedding, and accessibility contrast checks. Not a free-form website builder (correct). Starter media + uploads support “make it look like my shop” without AI.

Gaps: more templates (spec mentions Bakery/Bold/Quick Order), richer undo history, and ensuring preview never charges (staging/local already disable payments; production preview path should continue to avoid checkout side-effects).

**Status:** Strong pilot differentiator.

---

## 16 Media/storage readiness (+ per-tenant quota recommendation for ~$150/mo)

**Ready for pilot with limits.** Private storage port (`MediaStorage`), local + Supabase implementations, path `tenants/<organization-id>/...`, server-side authz before read, image validation (≤10 MB, dimension/pixel caps), optimization via Pillow, product `media_asset_id` on feature tip, starter library.

**Missing:** per-tenant quota / plan enforcement (only per-object caps).

**Recommendation for ~C$150/mo Core:**
- Soft quota **1 GB** active media / tenant (≈100–200 optimized product/brand images).
- Hard stop **1.5 GB**; warn at 80%.
- Max **500** active objects / tenant.
- Keep 10 MB / object; prefer WebP/JPEG optimization (already).
- Engagement/Pro can raise to 3–5 GB later.
- Track `sum(bytes)` on `media_assets` (add column if needed) and enforce in upload API.
- Staging disk is 1 GB shared (`render.staging.yaml`) — fine for review, not a multi-tenant prod model.

No runtime AI image generation dependency detected in app source (good).

---

## 17 Owner dashboard readiness

Admin shell covers orders, products, scheduling, customers, communications, loyalty, design, setup, launch, staff, platform. Capability-based owner auth and CSRF-protected mutations are present. Setup wizard reduces first-run friction. Residual Guest House naming in API is owner-invisible but cleanup still owed. Suitable for a training-assisted first merchant; copy still sometimes says Clover explicitly.

---

## 18 Security findings

**Positives**
- Tenant fail-closed resolution; no client-chosen org IDs.
- Fernet-encrypted Clover tokens; OAuth state single-use; webhook signature verification helpers.
- Auth session pepper; secure cookie flags configurable; Supabase secret server-only (documented).
- Staging refuses production integration credentials.
- Media private bucket pattern; path traversal checks in local storage.
- CSRF principal on mutating owner routes (pattern in platform/launch).
- Diagnostic redaction of sensitive Clover response fields.

**Gaps / risks**
- Missing `.env.example` increases misconfiguration risk.
- README references absent CLOVER/RENDER docs.
- Backend package/API still single-tenant branded (confusion risk, not direct exploit).
- No frontend lint/typecheck gate.
- Migration downgrade suite failing on tip — release-engineering smell (upgrade path still used in deploy).
- Staff PIN model needs continued brute-force/rate-limit vigilance in production config (foundation exists; confirm deployment settings).
- Service worker / PWA caching must not leak cross-tenant assets (host-scoped state helps; verify SW cache keys in prod).

No secrets were committed in the audited tree beyond documentation placeholders.

---

## 19 Test results

### Frontend
```text
npm run test:frontend
# tests 389
# pass 389
# fail 0
# duration_ms ~10206
```

### Frontend build
```text
npm run build  # vite v8.1.5 — success (~491ms)
# chunk size warning >500kB (non-blocking)
```

### Lint / typecheck / format
```text
package.json scripts: dev, build, build:staging, preview, test:frontend only
No eslint / prettier / typescript installed or scripted → N/A (honest gap)
```

### Backend
```text
Python 3.12.14 venv; TEST_DATABASE_URL=postgresql+psycopg://guesthouse:password@127.0.0.1:5432/guesthouse_test
PYTHONPATH=backend required for `from tests...` imports

Full suite: 20 failed, 323 passed, 2 warnings in ~56s
All failures: backend/tests/test_migrations.py
  - upgrade/downgrade / bootstrap / V1 downgrade-refusal parametrized cases
  - Likely interaction of head migration 20260903_31 (product media) with V1 platform downgrade safety guards expecting empty/nonbaseline media_assets constraints

Recheck isolation/media (explicit):
  test_tenant_catalog_isolation.py
  test_tenant_order_isolation.py
  test_tenant_clover_isolation.py
  test_v1_platform_isolation.py
  test_media_storage.py
  test_starter_media.py
→ all passed (55 tests)
```

**Interpretation:** Application functional + isolation confidence is high. Migration downgrade/bootstrap confidence on this tip is **not** green — fix before relying on downgrade/restore runbooks; forward `alembic upgrade head` deploys may still be OK but must be verified in staging.

---

## 20 Deployment architecture

| Surface | Stack |
|---|---|
| Customer/owner SPA | Netlify (`npm run build` → `dist`) |
| Staging SPA | `netlify.staging.toml` + API origin proxy; no `VITE_` secrets |
| API | Render Python service (`render.staging.yaml` template); Uvicorn; migrations pre-deploy |
| DB | Render PostgreSQL (staging dedicated) |
| Media | Staging local disk 1 GB; production intended Supabase private storage |
| Auth | Supabase Auth (prod); development/staging providers for review |
| Payments | Clover OAuth/Hosted Checkout (prod); disabled in staging review |

Production Render/Clover runbooks referenced but **files missing**. Auto-deploy disabled for staging review (good). No Supabase-as-primary-DB; Postgres is system of record.

---

## 21 Estimated scaling/cost concerns (10/50/100 tenants)

Assumptions: ~C$150/mo/tenant software; JDS not MoR; each shop pays its own processor fees.

| Tenants | Approx. platform cost drivers | Notes |
|---|---|---|
| **10** | Single Render API + Postgres, Supabase Auth/Storage, Netlify | Comfortable. Media ~10–15 GB worst case if quotas enforced. Support load dominates cost. |
| **50** | Upsize Postgres; consider separate worker for push drain; CDN for SPA | Watch webhook/reconcile volume; per-tenant Clover token refresh; storage quotas mandatory. Gross ~C$7.5k/mo software if all paying. |
| **100** | Likely need horizontal API, stronger observability, backup/DR drills, maybe read replicas | Support/onboarding automation becomes bottleneck before raw compute. Push fan-out and media bandwidth matter. |

Cost risks: unbounded media without quotas; chatty Clover reconciliation; web push delivery; lack of billing enforcement → free riders. Margin at C$150 is viable if infra stays lean and onboarding is self-serve (Design Studio helps).

---

## 22 P0 — blocks any real merchant

1. **Production packaging incomplete:** missing `.env.example` and referenced CLOVER/RENDER docs — high chance of unsafe/wrong production config.
2. **Verified canonical hostname + TLS storefront** must be provisioned for the merchant (readiness hard-requires it) — without a repeatable DNS/host mapping procedure, public storefront cannot go `public_ready`.
3. **Working shop-owned payment path for that merchant’s processor.** Today that means a correctly configured **Clover** OAuth installation + webhooks + Hosted Checkout page config. A non-Clover shop is blocked cold.
4. **Do not enable staging/local review flags or fixture payment mode in production** (guards exist — still an operational P0 checklist item).

---

## 23 P1 — must fix before first paying merchant

1. Repair **`test_migrations.py` failures** on `20260903_31` / V1 downgrade guards; confirm clean `upgrade head` on empty and staging DBs.
2. Introduce **payment port + rename readiness/UX off hard-coded Clover** even if Clover remains the only adapter (architecture debt otherwise becomes product debt on day one).
3. Wire **activation email / Supabase invite templates** for real owner onboarding (deferred delivery adapter is not enough for unattended signup).
4. Enforce **media quotas** and confirm Supabase private bucket production settings.
5. Decide and implement **JDS subscription collection** (trial → C$150 active) or manually invoice first merchant with entitlements seeded.
6. Smoke-test full path on staging-like + sandbox Clover: design → menu → publish → order → pay → fulfill → launch kit.
7. Remove or quarantine Guest House API titles / package name to avoid merchant confusion in support diagnostics.

---

## 24 P2 — acceptable shortly after launch

- Additional Design Studio templates (Bakery/Bold/Quick Order).
- Deeper Clover device/printer fulfillment options audit.
- Stronger analytics for owners.
- Custom domains beyond platform subdomains.
- Frontend lint/format/typecheck CI.
- Dual-write generic payment columns; deprecate `clover_*` on orders.
- Push engagement tier packaging polish.

---

## 25 P3 — future enhancement

- Second payment adapters (Square/Stripe/Moneris) **after** port exists.
- Native iOS/Android.
- SMS marketing, gift cards, delivery logistics, advanced CRM/loyalty automation.
- AI-generated imagery/design (explicitly not wanted at runtime now).
- Full website builder / arbitrary HTML/CSS.
- Enterprise multi-location.

---

## 26 Shortest path to first paying coffee shop

1. Pick one Clover-using Ontario (CAD/HST) café willing to pilot.  
2. Merge feature → main only after migration tests fixed and staging smoke passes (**not done in this audit**).  
3. Provision prod API + Postgres + Supabase Auth/Storage + Netlify using a newly written env runbook.  
4. Platform-provision merchant (or activation link); complete wizard: design, business, menu, hours, Clover connect, preview, launch.  
5. Verify hostname, place QR at counter, run 5 real sandbox then live orders end-to-end.  
6. Manually bill C$150 (or seed subscription) while SaaS billing is unfinished.  
7. Parallel track: implement payment port so the second shop is not forced onto Clover.

---

## 27 Recommended implementation milestones

1. **M0 — Release hygiene (≤3 days):** fix migration tests; add `.env.example`; restore/write CLOVER + RENDER docs; staging smoke checklist.  
2. **M1 — First Clover pilot (1–2 weeks):** production deploy, one tenant live, payment+fulfillment proven, media quotas, manual billing.  
3. **M2 — Payment boundary (1–2 weeks):** neutral port + frontend/readiness rename; Clover as adapter only.  
4. **M3 — SaaS billing (1 week):** collect ~C$150, trials/grace, entitlement enforcement on.  
5. **M4 — Scale onboarding (ongoing):** DNS automation, more templates, second processor only if demanded.

---

## 28 What Grok should build next

1. Migration suite fix for `20260903_31` downgrade/bootstrap compatibility (smallest possible).  
2. `.env.example` + missing production docs from README references.  
3. Payment port skeleton + cart/readiness indirection (Clover adapter wrapping current code).  
4. Media quota enforcement aligned to §16.  
5. Pilot runbook checklist document in `docs/`.

---

## 29 What should deliberately NOT be built yet

- Stripe/Square/Moneris full adapters before the neutral port exists.  
- Runtime AI image generation.  
- Native apps, SMS blasts, gift cards, delivery.  
- Full website builder / unrestricted design canvas.  
- Big-bang rewrite off the Ladel’s-derived commerce core.  
- Merging to main or production deploy as part of audit work.  
- Replacing Clover tables in place without dual-write.

---

## 30 Final market-readiness verdict (A|B|C) + readiness % with explanation

### Verdict: **B — CLOSE — COMPLETE LISTED WORK THEN PILOT**
### Readiness: **~70%** toward first paying Clover coffee shop; **~45%** toward processor-neutral market thesis

**Why not A:** Payment is not abstracted; production docs/env template missing; migration tests red on tip; SaaS fee collection unfinished; hostname/onboarding still needs operator care; product spec still Clover-centric.

**Why not C:** Multi-tenant isolation, Design Studio, catalog/orders/fulfillment, launch kit, staging safety, and large green test surface are already in place on `feature-production-image-foundation`. A careful Clover pilot is realistic after P0/P1 — not a greenfield rebuild.

**Explanation:** The branch is a credible branded-ordering SaaS MVP differentiated by Design Studio, with commerce maturity inherited from Ladel’s. Market rules require treating Clover as optional; architecture still treats Clover as mandatory. Close that gap and finish packaging, and the first ~C$150/mo coffee shop pilot is justified.

---

## Terminal summary

```text
COFFEE SAAS MARKET READINESS AUDIT COMPLETE
Repo: jds-branded-ordering
Branch: audit/market-readiness-20260910 (from feature-production-image-foundation @ be56dab)
Commit: see branch tip after docs commit (audited product tip be56dab71beef72cd9c2a5c7008bd328e186a849)
Tests: frontend 389/389 pass; build pass; backend 323 pass / 20 fail (all test_migrations.py); isolation/media recheck pass; lint/typecheck/format N/A
Current readiness: ~70% (first Clover coffee shop) / ~45% (processor-neutral thesis)
Verdict: B
P0: prod docs/env template; merchant hostname provisioning; working shop payment (Clover today) / non-Clover blocked
P1: fix migration tests; payment port + UX/readiness decoupling; activation email; media quotas; JDS fee billing; E2E smoke; branding cleanup
Payment architecture status: Clover-hardwired end-to-end; mock paymentService unused; abstraction missing
Design Studio status: Strong V1 differentiator (templates, draft/publish, phone preview, media) on feature tip
Multi-tenant status: Strong isolation spine + passing isolation tests; hostname ops still practical bottleneck
First paying customer blockers: prod packaging + hostname + Clover sandbox/live proof (or payment port if shop ≠ Clover); migration hygiene; billing method
Report: /workspace/jds-branded-ordering/GROK_COFFEE_SAAS_MARKET_READINESS_AUDIT.md
Recommended next milestone: M0 release hygiene (migration tests + env/docs) then M1 single Clover café pilot
```
