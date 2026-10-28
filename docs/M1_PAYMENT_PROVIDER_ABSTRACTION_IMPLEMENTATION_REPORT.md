# M1 Payment Provider Abstraction — Implementation Report

**Date:** 2026-09-10 (America/Toronto)  
**Branch:** `m1/payment-provider-abstraction` @ `8f09e6c`
**PR:** https://github.com/mjacquot82-svg/jds-branded-ordering/pull/3 (open, **not merged**)  
**Base:** `origin/feature-production-image-foundation` @ `2fd55d2` (M0 PR #2 merge)  
**Production deploy:** none  
**PR merge:** not performed (open PR only)

---

## 1. Executive summary

M1 introduces a smallest-safe provider-neutral payment port, wraps existing Clover behavior behind a Clover adapter, adds tenant payment settings + generic order payment fields (additive migration), switches cart checkout to `/api/v1/payments/...`, and renames readiness to `payment_connected` (with `clover` alias). Stripe/Square/Moneris adapters were **not** implemented. Clover remains the only enabled adapter.

## 2. Starting-state verification

| Check | Result |
| --- | --- |
| Repo | `/workspace/jds-branded-ordering` |
| M0 PR #2 | **MERGED** into `feature-production-image-foundation` |
| Merge commit | `2fd55d2634ab5033dd6b2d85380fdbde931ae5a4` |
| M1 base tip | `origin/feature-production-image-foundation` @ `2fd55d2` |
| Design doc | `docs/M1_PAYMENT_PROVIDER_ABSTRACTION.md` verified against code |

## 3. Design-doc deltas (code-proven)

Documented in design §9. Key deltas: dual-write (keep `clover_*` columns), readiness alias `clover`, fail-closed checkout without silent Clover fallback, readiness may materialize `provider_key=clover` when a connected installation already exists.

## 4. Scope respected / non-goals

- No merge into feature branch by agent  
- No production deploy  
- No Stripe/Square/Moneris adapters  
- No new Clover marketplace features  
- No JDS subscription billing / SMS / Design Studio / Guest House / speculative payment features  
- Clover not rewritten — isolated behind port  

## 5. Branch / commits / PR

- Branch: `m1/payment-provider-abstraction` from `2fd55d2`  
- PR target: `feature-production-image-foundation`  
- PR URL: https://github.com/mjacquot82-svg/jds-branded-ordering/pull/3  

## 6. Interface (port)

Path: `backend/app/payments/port.py`

- `PaymentProvider` protocol: `connection_status`, `create_checkout`, `reconcile`, `handle_webhook`, `refund`  
- DTOs: `CheckoutSession`, `ConnectionStatus`, `PaymentStatusResult`, `NormalizedPaymentEvent`, `RefundResult`, `ReturnUrls`

## 7. Adapter paths

- Clover: `backend/app/payments/adapters/clover_adapter.py`  
- Registry: `backend/app/payments/registry.py` (`SUPPORTED_PROVIDERS={"clover"}`)  
- Orchestration: `backend/app/payments/service.py`  
- Order dual-write helpers: `backend/app/payments/order_payment.py`

## 8. Generic API

- `POST /api/v1/payments/orders/{public_token}/checkout`  
- `GET /api/v1/payments/connection`  
- Legacy `/api/v1/clover/...` retained (OAuth, checkout façade, webhooks, reconcile)

## 9. Tenant payment configuration

Table `organization_payment_settings(organization_id PK, provider_key, encrypted_config, …)`  
Known keys: clover|stripe|square|moneris. Only **clover** enabled for real checkout. No fake credentials for unsupported providers.

## 10. Order / payment data model

Additive nullable columns on `orders`: `payment_provider`, `payment_status`, `payment_checkout_ref`, `payment_redirect_url`, `payment_expires_at`, `payment_provider_txn_id`, `payment_failure_code`, `payment_paid_at`, `payment_provider_metadata`.  
Clover columns retained; dual-written on checkout/paid. Generic `payment_events` table added (adapters may still use `clover_payment_events`).

## 11. Webhooks

Clover adapter owns signature validation + normalized event mapping (`handle_webhook`). Persistence/idempotency/tenant resolution remain in existing Clover façade for M1 (security preserved).

## 12. Fail-closed behavior

Missing settings or unsupported `provider_key` → clear `503` with codes `payment_provider_not_configured` / `payment_provider_unsupported`. **No** silent Clover fallback on checkout even if a Clover installation exists.

## 13. Unpaid / manual

`payment_status=manual_unpaid|unpaid` must never look electronically paid (`assert_not_false_paid`). Client `confirmPayment` no longer invents paid. Guidance: `docs/MANUAL_AND_PAY_AT_PICKUP.md`.

## 14. Migrations

Revision `20260910_32` — additive, reversible downgrade, backfills generic fields from Clover checkout evidence, inserts settings for connected Clover orgs. Tenant-safe (org-scoped).

## 15. Frontend changes

- `src/services/paymentService.js` — real generic client  
- `CartPage.jsx` → `createCheckout`  
- Owner UX prefers `payment_connected` with `clover` fallback  
- `cloverService.js` remains for OAuth/admin Clover connection  

## 16. Architectural proof (second provider without core rewrite)

To add Square/Stripe/Moneris **without** rewriting cart/order/storefront core:

1. Implement `PaymentProvider` in `backend/app/payments/adapters/<provider>_adapter.py`  
2. Register in `registry.get_provider` + add to `ENABLED_PROVIDER_KEYS` when ready  
3. Add provider routes under `/api/v1/payments/{provider}/...` for OAuth/webhooks  
4. Owner settings UI selects `provider_key` (schema already supports it)  
5. Cart continues calling `/api/v1/payments/orders/{token}/checkout` only  

**Verdict on proof:** A (core cart/order services do not import provider SDKs; registration is adapter+registry).

## 17. Required scenarios covered (12)

1. Only clover enabled in registry  
2. Unsupported provider fails closed (no Clover fallback)  
3. Second-provider registration is port-only (FakeSquare proof)  
4. Manual/unpaid never looks electronically paid  
5. `mark_electronically_paid` sets generic fields  
6. Missing settings → checkout fail closed despite Clover install  
7. Unsupported key in settings → fail closed  
8. Clover tenant checkout via generic `/payments` API + dual-write  
9. Generic checkout rejects when provider missing  
10. Readiness exposes `payment_connected` + `clover` alias  
11. Tenant payment settings org-scoped  
12. Clover adapter webhook signature validation  

## 18. Test / build matrix (real results)

| Suite | Result |
| --- | --- |
| Backend full pytest | **356 passed**, 0 failed |
| `test_payment_provider_abstraction.py` | 12 passed |
| Isolation + media + migrations + payment | passed |
| Frontend `npm run test:frontend` | **392/392 pass** |
| `npm run build` | **pass** (513ms) |

## 19. Clover regression status

Existing Clover integration/isolation/orders tests remain green in full suite. Legacy `/clover` routes retained; dual-write keeps webhook identity fields.

## 20. Commercial / security reminders

JDS is **not** merchant of record; no % of sales; tenant-owned credentials; server secrets never exposed to browser; logs avoid secrets.

## 21. Files changed (summary)

New: `backend/app/payments/**`, `backend/app/api/v1/payments.py`, migration `20260910_32`, tests, `docs/MANUAL_AND_PAY_AT_PICKUP.md`, FE `paymentService` tests.  
Modified: clover API dual-write, readiness, orders model, migrate bootstrap exclusions, Cart/owner UX, design deltas.

## 22. How to add a second provider (short)

Implement adapter → enable in registry → OAuth/webhook routes → select `provider_key` in settings. No CartPage/orders domain rewrite required.

## 23. Remaining P0 / P1

**P0:** Stripe/Square/Moneris real adapters for non-Clover cafés; production Clover sandbox E2E still recommended; DNS/secrets packaging (ops).  
**P1:** Drop obsolete `clover_*` order columns after dual-read window; expose refunds via port; richer owner provider picker UX; pay-at-pickup staff action; remove readiness `clover` alias after FE fully migrated.

## 24. Blockers

None for merging M1 into the feature branch. First **non-Clover** real café still blocked until a second adapter ships. Clover cafés unblocked pending production env/E2E.

## 25. Verdict

**A** — Port + Clover adapter + tenant settings + generic fields + fail-closed + architectural proof that a second provider is adapter/registry-only; suites green; PR opened not merged.

---

### Terminal summary block

```
M0 merge: PR #2 MERGED @ 2fd55d2634ab5033dd6b2d85380fdbde931ae5a4
M1 branch: m1/payment-provider-abstraction (from feature tip 2fd55d2)
Backend: 356 passed
Frontend: 392/392 pass
Build: pass
Isolation/migrations/payment: pass
Clover regression: green (legacy routes + dual-write)
Verdict: A
Deploy: none | Merge: none (PR only)
```
