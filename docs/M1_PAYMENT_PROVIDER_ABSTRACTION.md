# M1 — Payment provider abstraction (DESIGN ONLY)

**Status:** Design document. Do **not** implement adapters or rewrite checkout in M0/M1-design.
**Product framing (roadmap correction):** M1 is **not** “first Clover café pilot.”
The product target is a **processor-neutral multi-tenant SaaS**. After M0/M1
boundary work, the first real coffee shop must be able to use
jds-branded-ordering **regardless of whether its existing processor is Clover**.
Clover remains the first *working* adapter later; it must not determine whether
a tenant can use the platform.

**Commercial model reminder:** Merchant owns the payment account; JDS is **not**
Merchant of Record; JDS does **not** take a percent of transactions. Platform fee
billing is a separate concern (out of scope here).

---

## 1. Goal

Convert today’s Clover-hardwired checkout path so **core ordering** deals only in
generic concepts, while **provider adapters** own processor specifics.

### Generic core concepts

| Concept | Meaning |
| --- | --- |
| Order | Tenant-scoped cart commitment (items, totals, pickup, customer) already in `orders` |
| Checkout / payment intent | Request to collect funds for an order; returns a client redirect or client secret |
| Payment status | `requires_action` / `pending` / `paid` / `failed` / `cancelled` / `refunded` (exact enum TBD in implementation) |
| Refund / cancellation boundary | Core requests refund/cancel; adapter executes against provider APIs + evidence |
| Webhook events | Normalized events (`payment.succeeded`, `payment.failed`, `refund.updated`, …) with provider raw payload retained for audit |

### Adapter responsibilities

- OAuth / credential connect & refresh (Clover today; Stripe Connect / Square / Moneris later)
- Creating provider checkout/payment sessions
- Verifying webhooks and mapping to normalized events
- Idempotent reconciliation of provider payment IDs → order payment status
- Provider-specific error codes → stable API errors

---

## 2. Complete map of current Clover dependencies

Classification:

- **CORE-ORDERING** — needed for any processor; today carries Clover-shaped fields or calls that must become generic.
- **CLOVER-SPECIFIC** — belongs in a Clover adapter package.

### Backend

| Path | Class | Notes |
| --- | --- | --- |
| `backend/app/clover/config.py` | CLOVER-SPECIFIC | `CLOVER_*` env loading/validation |
| `backend/app/clover/client.py` | CLOVER-SPECIFIC | OAuth + Hosted Checkout HTTP client |
| `backend/app/clover/security.py` | CLOVER-SPECIFIC | Token encryption, state, webhook HMAC |
| `backend/app/clover/models.py` | CLOVER-SPECIFIC (table) → later behind port | `clover_installations`, `clover_payment_events` |
| `backend/app/api/v1/clover.py` | CLOVER-SPECIFIC API | OAuth, connection, `create_hosted_checkout`, webhooks, reconcile |
| `backend/app/api/v1/router.py` | CORE-ORDERING (wiring) | Mounts clover router; later mounts `/payments` + adapter routes |
| `backend/app/orders/models.py` | CORE-ORDERING (contaminated) | `clover_*` checkout columns + `ck_orders_clover_checkout_consistent` + FK to `clover_installations` |
| `backend/app/orders/service.py` / `repository.py` / `schemas.py` | CORE-ORDERING | Order create/read; keep free of provider SDK calls (mostly clean today) |
| `backend/app/api/v1/orders.py` | CORE-ORDERING | Pending order APIs; checkout is separate clover route today |
| `backend/app/platform/readiness.py` | CORE-ORDERING (contaminated) | Hard-coded `"clover"` readiness check |
| `backend/app/api/v1/platform.py` | CORE-ORDERING (contaminated) | Onboarding step `"clover"`, platform admin Clover warnings/masks |
| `backend/app/platform/acquisition.py` | CORE-ORDERING | Mentions provider-neutral acquisition; keep Clover out of required path |
| `backend/app/local_review_seed.py` / staging seeds | CLOVER-SPECIFIC fixtures | May seed Clover connection for review |
| `backend/app/db/migrate.py` | CORE-ORDERING bootstrap | Knows Clover table/column names for legacy adopt |
| Migrations `20260729_04`, `20260818_20`, `20260822_25`, seeds in `20260823_26` | CLOVER-SPECIFIC schema history | Preserve; new generic tables via forward migrations |
| Tests `test_clover_integration.py`, `test_tenant_clover_isolation.py`, parts of `test_orders_api.py`, `test_v1_platform_isolation.py`, `test_migrations.py` | mixed | Keep Clover tests; add port/contract tests later |

### Frontend

| Path | Class | Notes |
| --- | --- | --- |
| `src/services/cloverService.js` | CLOVER-SPECIFIC | `createCloverCheckout`, connection helpers |
| `src/services/checkoutOrder.js` | CORE-ORDERING (contaminated) | Imports `CloverCheckoutError`; should depend on generic payment client |
| `src/services/paymentService.js` | CORE-ORDERING stub | Unused mock `confirmPayment` — replace with real port client later |
| `src/pages/CartPage.jsx` | CORE-ORDERING (contaminated) | Calls `createCloverCheckout` directly |
| `src/pages/ConfirmationPage.jsx` | CORE-ORDERING | Payment confirmation UX; may assume Clover return URLs |
| `src/admin/OrdersPage.jsx` | CORE-ORDERING | May surface Clover payment fields |
| `src/admin/OnboardingPage.jsx`, `SetupWizard.jsx`, `LaunchPage.jsx`, `DesignPreviewPage.jsx`, `AdminDashboard.jsx`, `PlatformAdminPage.jsx` | CORE-ORDERING UX | “Connect Clover” step copy/checks → “Connect payments” + provider-specific panel |
| `src/services/notificationService.js` | incidental | Review for Clover wording only |

### Env

All `CLOVER_*` variables are **CLOVER-SPECIFIC**. Core runtime must boot without them when no tenant uses Clover (today readiness/onboarding still assume Clover — that coupling is what M1 removes).

---

## 3. Smallest safe interface / boundary

Keep the existing Clover HTTP surface working during transition. Introduce a thin
port used by storefront checkout and readiness — **do not fork** the storefront
or order system.

```text
# Proposed module (future): backend/app/payments/port.py

class PaymentProvider(Protocol):
    key: str  # "clover" | "stripe" | "square" | "moneris" | ...

    def connection_status(self, organization_id: UUID) -> ConnectionStatus: ...
    def create_checkout(self, order: Order, *, return_urls: ReturnUrls) -> CheckoutSession: ...
    def reconcile(self, order: Order) -> PaymentStatus: ...
    def handle_webhook(self, headers, body: bytes) -> list[NormalizedPaymentEvent]: ...
    def refund(self, order: Order, amount_cents: int | None) -> RefundResult: ...
```

Suggested stable DTOs (names illustrative):

- `CheckoutSession{ provider, provider_ref, redirect_url?, client_secret?, expires_at }`
- `NormalizedPaymentEvent{ type, provider, provider_payment_ref, order_public_token?, amount_cents?, raw_event_id }`
- `ConnectionStatus{ connected: bool, provider, display_hint, environment }`

### Routing pattern (phased)

1. **Phase A:** Extract Clover logic behind `CloverPaymentProvider` implementing the port; `api/v1/clover.py` becomes a thin adapter façade (URLs unchanged).
2. **Phase B:** Add `POST /api/v1/orders/{token}/checkout` (generic) that selects the tenant’s provider and delegates. Cart UI switches to this endpoint.
3. **Phase C:** Readiness/onboarding use `payment_provider_connected` instead of `clover`.
4. **Phase D:** Add Stripe/Square/Moneris adapters without touching cart/order core.

Existing Clover OAuth/webhook URLs stay for installed apps; new providers get their own `/api/v1/payments/{provider}/...` routes.

---

## 4. Tenant provider selection & credential isolation

### Storage model (recommended)

| Data | Where | Isolation |
| --- | --- | --- |
| Selected provider key | New `organization_payment_settings(organization_id PK, provider_key, updated_at)` | One active provider per tenant initially |
| Provider credentials / tokens | Provider-specific tables **or** single `payment_installations` with `provider_key` + encrypted JSON blob | Always `organization_id` scoped; composite FKs like today’s Clover tenant spine |
| Checkout evidence on order | Replace naked `clover_*` columns with nullable generic `payment_provider`, `payment_installation_id`, `payment_checkout_ref`, `payment_redirect_url`, `payment_expires_at` (+ optional provider jsonb for overflow) | Tenant FK already on `orders` |
| Webhook / payment events | `payment_events(organization_id, provider_key, provider_event_id UNIQUE, payload, ...)` | No cross-tenant reads |

### Security rules

- Encrypt secrets at rest with a platform key (today `CLOVER_TOKEN_ENCRYPTION_KEY`; generalize to `JDS_PAYMENT_TOKEN_ENCRYPTION_KEY` or per-provider keys).
- Never expose refresh/access tokens to the browser.
- Merchant owns the processor account (OAuth to **their** Clover/Stripe/Square/Moneris entity).
- JDS never settles card funds; no MoR; no % take in this design.
- Platform operators see masked merchant references only (existing Clover admin masking pattern).

### Selection UX

Owner Settings → Payments: choose provider → connect (OAuth or API keys per adapter). Switching providers while open checkouts exist must be blocked or carefully drained.

---

## 5. Migration / phasing plan (no rewrite)

1. **Document + readiness language (M0):** stop calling M1 a Clover-only café pilot; keep Clover working.
2. **Introduce port + wrap Clover (implementation M1 start):** zero behavior change; tests still green.
3. **Generic order payment columns:** additive migration; backfill from `clover_*`; keep old columns readable until dual-write period ends.
4. **Generic checkout API + frontend client:** Cart uses port; `cloverService.js` becomes adapter or shrinks.
5. **Readiness rename:** `clover` check → `payment_connected` reading port; onboarding step id update with backward-compatible alias.
6. **Only then** implement Stripe/Square/Moneris adapters (explicitly **not** in M1 design phase).
7. Drop obsolete `clover_*` order columns only after adapters + dual-read window.

Rollback story: feature-flag generic checkout route; Clover façade URLs remain.

---

## 6. Explicit non-goals (M1 implementation phase)

When implementation begins, still **out of scope** unless separately chartered:

- Building Stripe / Square / Moneris adapters
- JDS subscription billing / invoicing / MoR
- Percent-of-GPV monetization
- Rewriting the order/catalog/design systems
- Removing the working Clover path
- Multi-provider simultaneous checkout per tenant
- Production deploy as part of design merge

---

## 7. Acceptance criteria for a future implementation PR

- Core checkout UI has no direct imports of Clover SDK/URLs.
- A tenant with provider=`clover` behaves identically to today (regression suite).
- A tenant with no provider fails readiness on `payment_connected`, not on a hard-coded Clover label alone.
- Adding a new adapter does not require editing `CartPage` or `orders` domain services beyond registration.
- Secrets remain server-side and tenant-scoped.

---

## 8. Related docs

- `.env.example` — Clover vs provider-neutral env classification
- `docs/MERCHANT_HOSTNAME_PROVISIONING.md` — tenancy routing (not payments)
- `docs/PRODUCTION_DEPLOYMENT.md` — optional Clover adapter enablement
