# M2 Self-Service Demo-to-Customer Funnel — Implementation Report

**Date:** 2026-09-10 (America/Toronto)  
**Branch:** `m2/self-service-demo-funnel` @ `7369930`  
**PR:** https://github.com/mjacquot82-svg/jds-branded-ordering/pull/4 (open, **not merged**)  
**Base:** `feature-production-image-foundation` @ `4195c10fdf39048ba39d34a9d85802b6a42c701b`  
**Production deploy:** none  
**PR merge:** not performed (open PR only)

---

## 1. Executive summary

M2 adds a server-enforced free-prospect demo funnel on the existing multi-tenant Design Studio / catalog / media stack. A coffee-shop owner can create an account, build a convincing branded demo (Harbor & Hearth starter — not Guest House/Ladel's), save/return/preview, and **request activation** for a centrally priced ~C$150/mo live plan while real orders/payments stay fail-closed. Design, catalog, and media are preserved on JDS promote-to-live. No Stripe/Square/Moneris adapters, no automated subscription billing, no permanently free live ecommerce.

## 2. Starting-state verification

| Check | Result |
| --- | --- |
| Clone | `/workspace/jds-branded-ordering` |
| Base SHA | `4195c10fdf39048ba39d34a9d85802b6a42c701b` (clean) |
| Branch created | `m2/self-service-demo-funnel` from that SHA |
| M1 | Present on base (payment abstraction + Clover dual-write) |

## 3. Phase 1 audit / plan (architecture-adapted)

Existing pieces reused rather than reinvented:

- **Organizations** `lifecycle_status` kept (`onboarding|active|suspended|archived`)
- **New `commercial_mode`**: `prospect` vs `live` (server source of truth for FREE vs PAYING)
- **MerchantAcquisition** source `self_service_demo`; activation request sets acquisition `activation_pending`
- **BillingPlan** `jds-demo` / `jds-standard` + `billing_plan_pricing` (CAD cents, JDS take fixed at 0%)
- **Design Studio / catalog / media** unchanged architecture; demo starter seeds real tables
- **Preview**: existing authenticated `/owner/design/preview` with `checkoutEnabled: false`
- **Auth**: existing IdentityProvider register + password; no anonymous ownership

## 4. Scope respected / non-goals

- No auto-merge into feature branch; no production deploy  
- No new payment providers; no new Clover features; M1 fail-closed intact  
- No automated JDS subscription billing (REQUEST ACTIVATION only)  
- No permanently free live ecommerce; no real orders/payments for prospects  
- No unlimited AI generation / storage; no second free application  
- Additive migration only; Clover columns retained  

## 5. Branch / commits / PR

- Branch: `m2/self-service-demo-funnel` from `4195c10`  
- PR target: `feature-production-image-foundation`  
- PR URL: https://github.com/mjacquot82-svg/jds-branded-ordering/pull/4

## 6. Lifecycle model

| Layer | Values |
| --- | --- |
| `organizations.commercial_mode` | `prospect` (free demo) / `live` (paying/legacy) |
| `organizations.lifecycle_status` | existing onboarding/active/suspended/archived |
| Acquisition status | activated on signup; `activation_pending` while lead open |
| Activation request status | requested/in_review/approved/rejected/withdrawn |
| Subscription plan | `jds-demo` while prospect; `jds-standard` after promote |

## 7. Signup / auth

- `POST /api/v1/demo/signup` — email/password + business name via existing IdentityProvider  
- Unverified identity → `verification_required` + pending signup row (no anonymous org ownership)  
- `POST /api/v1/demo/enter` — verified sign-in claims pending or re-enters prospect  
- Session includes `commercial_mode`

## 8. Landing / starter

- FE `/build` — “Build Your Store Free”  
- Starter: **Harbor & Hearth Café** (fictional), cozy template, limited real catalog (9 products / 3 categories), ordering_enabled=false  

## 9. Demo capabilities

Name, logo, template, colours, fonts, imagery, phone preview, storefront auth preview, save/return/edit, limited catalog on real Product/Category tables.

## 10. Exact demo limits

| Limit | Value |
| --- | --- |
| Max products | **25** |
| Max categories | **8** |
| Max media files | **20** |
| Max total storage | **25 MiB** |
| Max per-file | **5 MB** |
| MIME | png/jpeg/webp |
| Max dimensions | 12000×12000 (platform) |
| Retention inactive days (policy) | 90 |
| Auto-delete in M2 | **false** (policy only) |

## 11. Commerce lockout

- `enforce_live_commerce` / `enforce_not_self_upgrade` (side-session read to avoid txn clashes)  
- Blocks: order create, generic + Clover checkout, Clover OAuth, staff invite, owner launch self-upgrade, hostname choose, design publish-to-live  
- Prospects cannot flip `commercial_mode` via API tampering  

## 12. Preview model

Authenticated owner design preview only; `checkoutEnabled: false`; no public storefront readiness (`organization` check requires `commercial_mode=live`); no production custom domain for free demos.

## 13. Activation conversion

- `/admin/go-live` shows configurable ~C$150/mo, JDS **0% of sales**, processor fees by merchant provider  
- Action = **Request activation** → `demo_activation_requests` lead  
- Preserve design/catalog/media; JDS `promote-to-live` flips commercial_mode without discarding assets  

## 14. Activation form fields

business name, contact name, email, optional phone, city, optional desired domain, processor preference (clover|square|stripe|moneris|other|not_sure) — info only.

## 15. Funnel events

`demo_started`, `logo_added`, `branding_changed`, `menu_edited`, `preview_opened`, `demo_saved`, `activation_viewed`, `activation_requested` — stored in `demo_funnel_events` (no analytics vendor).

## 16. Admin visibility

Platform admin: demo prospects list, recent activity, activation requests (business, email, processor, created_at, status), promote-to-live.

## 17. Abuse protections

Signup/enter/activation rate limits; upload validation (MIME/size/dimensions); demo caps; pending signup expiry 7 days. **Before paid ads:** CAPTCHA/bot scoring, stricter IP velocity, media virus scanning, email domain denylist, human review queue SLAs.

## 18. Data retention policy (no auto-delete)

Inactive prospects may be reviewed after **90 days**. M2 does **not** auto-delete. Future deletion requires tested soft-archive + owner notification.

## 19. Pricing configuration

- Env: `JDS_STANDARD_PLAN_MONTHLY_CAD` (default 150) or `JDS_STANDARD_PLAN_MONTHLY_CENTS`  
- Table `billing_plan_pricing` with check `jds_sales_take_percent = 0`  
- Public `GET /api/v1/demo/pricing`

## 20. Migration

Revision `20260910_33` additive: `commercial_mode`, pricing table, pending signups, activation requests, funnel events, seed plans. Downgrade removes M2 artifacts only. Does not remove M1 `clover_*` fields.

## 21. Frontend changes

- `BuildStoreLandingPage`, `GoLiveActivationPage`, `demoFunnelApi.js`  
- Design Studio prospect banner + Go Live stage  
- Platform admin prospects/activations  
- Routes `/build`, `/admin/go-live`

## 22. Backend modules

`platform/commercial.py`, `demo_limits.py`, `demo_starter.py`, `demo_service.py`, `api/v1/demo.py`; lockouts wired into orders/payments/clover/platform/owner_catalog/owner_auth/readiness.

## 23. Required scenarios (20)

Covered in `tests/test_self_service_demo_funnel.py` (migration, signup starter, prospect vs live, commerce lockout, no self-upgrade, pricing 0% take, activation preserve, promote preserve, product/media limits, limits docs, enter, verification gate, preview checkout false, admin visibility, processor info-only, funnel whitelist, starter not GH/Ladel's, M1 clover fields, same-tenant architecture).

## 24. Test / build matrix (real results)

| Suite | Result |
| --- | --- |
| Backend full pytest | **376 passed**, 0 failed |
| `test_self_service_demo_funnel.py` | **20 passed** |
| Migrations | **passed** (incl. downgrade cleanup) |
| Frontend `npm run test:frontend` | **395/395 pass** |
| `npm run build` | **pass** (~504ms) |

## 25. Product success question

**YES.** Evidence: signup → prospect org + Harbor starter catalog/design → Design Studio save/preview (checkout disabled) → activation request lead → promote-to-live preserves design/media/catalog; orders/payments fail-closed while prospect.

## 26. M1 / Clover regression

Payment abstraction tests green; clover columns present; dual-write paths untouched except commerce lockout guards.

## 27. Isolation / security

Tenant media/catalog isolation suites green; demo reads use side-session for commercial mode to avoid txn interference; no weakening of CSRF/auth.

## 28. Stop conditions

None hit. No destructive migration, no major auth rewrite, no paid external service, no significant recurring infra, no M1 architecture rewrite, no security tradeoff requiring product-owner decision beyond documented ad-readiness hardening.

## 29. Remaining blockers / follow-ups

- Wire production Supabase email verification UX polish for `/build/verify`  
- Before paid ads: CAPTCHA + stricter abuse controls  
- Ops: JDS review SLA for activation leads  
- Optional: signed shareable preview tokens (auth preview sufficient for M2)  

## 30. Files changed (summary)

New: demo API/service/limits/starter/commercial, migration 33, FE landing/go-live/api, M2 tests+report.  
Modified: orders/payments/clover/platform/owner_catalog/owner_auth/readiness/models/schemas/acquisition/App/DesignStudio/PlatformAdmin/CSS/env/migrations tests.

## 31. How promote-to-live works

Platform grant holder calls `POST /api/v1/platform/admin/organizations/{id}/promote-to-live` → `commercial_mode=live`, plan `jds-standard`, approve open activation requests; **does not** delete design/catalog/media; owner still completes payment/hostname launch for `public_ready`.

## 32. Commercial disclosure (customer-facing)

Flat monthly software fee (~C$150 configurable). **JDS takes 0% of sales.** Processor fees still apply via the merchant’s provider.

## 33. Verdict

**A** — Success question YES; limits enforced; commerce fail-closed; activation preserves assets; suites green; PR opened not merged; no stop-condition hits.

## 34. Terminal summary block

```
Base SHA: 4195c10fdf39048ba39d34a9d85802b6a42c701b
M2 branch: m2/self-service-demo-funnel
Backend: 376 passed (incl. 20 M2 scenarios + migrations)
Frontend: 395/395 pass
Build: pass
Commerce lockout: server enforce_live_commerce (orders/payments/clover/staff/launch)
Limits: 25 products / 8 categories / 20 files / 25MiB / 5MB/file
Activation: request lead + promote-to-live preserves design/catalog/media
Success question: YES
Verdict: A
Deploy: none | Merge: none (PR only)
Stop conditions: none
```
