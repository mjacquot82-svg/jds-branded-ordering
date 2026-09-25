# M3 — Starter image library & SaaS completion report

Branch `m3/starter-image-library-and-saas-completion`, based on `m2.5/controlled-demo-launch` @ `8538fedbccd3e2753b9b792743fb7a72901be3b2`.

## What changed

- **Starter image library.** 26 original JDS illustrated placeholder images (1200 × 1200 WebP, ~463 KB in total) ship in the backend package. Code: `backend/app/platform/starter-media/cafe-restaurant/`, the generator is `backend/scripts/generate_starter_media.py` and `starter_art.py`. The manifest has `artStyle: "illustrated-placeholder"` and a provenance note. The other 44 planned archetypes stay hidden until art exists. See `docs/STARTER_MEDIA_ASSET_MANIFEST.md`.
- **Platform images vs merchant images.** Starter images are platform-owned and referenced as `starter:<collection>/<key>@<version>` in the existing `products.image_reference` column. They create no `media_assets` rows and never count against the prospect allowance. Merchant uploads stay tenant-owned `media_assets` rows, served through tenant-scoped owner endpoints. Cross-tenant references are refused.
- **Harbor & Hearth.** All 9 starter products get a matching starter illustration. The demo's hero content defaults to the canonical `cta` value, so a freshly loaded design no longer looks "unsaved".
- **Owner preview.**
  - Starter images and uploads resolve without a storefront hostname.
  - Images load eagerly and show at 4:3 instead of a 70px strip.
  - Modern-layout rows scroll sideways instead of clipping products.
  - The catalog stays within the phone width.
  - Free demos without their own hero photo get an intentional starter hero. It shows the business name, the tagline, three starter illustrations, a readable disabled "Start an order" button and "Ordering opens after activation".
- **Product editor.**
  - The picker offers only shipped art, with friendly category names, suggestions for the product name, a live card preview and a source badge.
  - A "not saved yet" prompt with a Save button appears after choosing an image.
  - The prospect 5 MB per-file check runs before upload.
  - Owners can see their photo allowance and use "Delete unused photo". The backend refuses to archive media used by a product or the draft design.
  - The picker search resets when switching products.
  - Categories panel buttons are styled and 44px tall.
  - On phones, Edit is the prominent action and the secondary actions sit in a compact 2-column grid.
- **Setup wizard (prospects).**
  - The Payments step has no Connect Clover.
  - The launch step becomes "Request activation", using the embedded activation form.
  - Preview checks use plain language and hide activation-only items.
  - At 375px: all 8 progress steps are visible, fields stack, and the footer Back button is fixed.
- **Neutral JDS branding.** `/build`, `/setup`, `/owner`, `/admin`, `/staff`, `/activate` and `/go-live` get the JDS title, icon and theme colour, and tenant CSS variables are cleared there. Customer storefront pages keep tenant branding.
- **Platform.**
  - Promote-to-live now requires `platform.organizations.write`. Local and staging seeds already grant read+write; read-only admins see "Promote requires platform write access."
  - `/admin/platform` deep links wait for capabilities instead of bouncing to Overview.
  - Prospect and activation times show in local time.

## Migrations

None. Starter references reuse `products.image_reference`, and the allowance and archive checks use existing tables.

## DB connection pool fix (pre-existing bug found during M3 E2E)

**Root cause.** Every owner request checks out up to three pooled connections, one after another:
1. `current_principal` → `get_auth_service` → `get_db_session`, in the threadpool. Released at its `commit()`.
2. `authenticated_owner_tenant`, a short-lived `session_factory()` session. It was an **`async def`**, so this blocking checkout ran **on the event loop**.
3. The endpoint's `get_catalog_session`, in the threadpool. Held until dependency teardown, which the event loop schedules.

When the pool (5 + 5 overflow, 30s timeout) was momentarily empty, step 2 blocked the event loop. No in-flight request could then finish or run its teardown to return a connection, so the waiter timed out after 30s (`QueuePool limit of size 5 overflow 5 reached`).

Two smaller hold-and-wait sources:
- `commercial._read_mode` (`is_prospect`) opened a side `Session` while the request's transaction still held a connection. `POST /owner/catalog/products` peaked at 2 connections per request.
- `upload_media` (must be `async` to read the body) made its first DB checkout on the event loop.

**Reproduction.** At the production pool settings, one prospect's 25 concurrent owner GETs (about one wizard page load) gave **10 × 200 and 15 × TimeoutError** in every round, taking 90–120s per round.

**Fix.** No pool-size change, and no change to auth, CSRF or tenant-resolution logic:
- `backend/app/api/v1/tenant_context.py`: `authenticated_owner_tenant` changed from `async def` to `def`, so FastAPI runs it in the threadpool. The body and its errors are identical.
- `backend/app/platform/commercial.py`: `_read_mode` reuses the caller's session when a transaction is already open. It does a column-level `SELECT`, which is still a fresh read and doesn't touch the identity map. Otherwise it uses the side session as before. An unknown organization still returns `live` (unchanged).
- `backend/app/api/v1/platform.py`: new sync dependency `upload_catalog_session` checks out the upload's connection in the threadpool (`session.connection()`). Same session and transaction semantics.

**After.**
- 25, 40, 50, 60 and 70 concurrent owner requests at the production settings: all 200, about 0.4–0.8s per burst, and the checked-out count returns to 0.
- Tests: `backend/tests/test_owner_db_pool_m3.py` (8 tests). On the old code, 6 fail, including QueuePool TimeoutErrors in the burst, save and upload tests. The 2 fail-closed tests pass on both old and new code with identical status codes: 401, 403 for client-supplied tenant context, 404 cross-tenant, 404 `tenant_not_found`, 500 on a DB error during tenant resolution, and 401 `session_expired` for an inactive membership. With only the tenant-dependency change, the 2 per-request single-connection and upload tests still fail, which is why the two smaller changes are included.

## Guest House storefront

Verified unchanged. Screenshots of `/`, `/menu`, `/cart` and `/account/sign-in` at 375px and 1280px from the base commit and from this branch are **pixel-identical**, and the title is still "The Guest House · Order online". All new CSS is scoped to owner/preview classes (`.full-design-preview`, `.layout-product-grid`, `.demo-hero*`, `.category-management-list`, `.product-row-actions`, `.product-image-save-hint`, wizard classes).

## Known limitations / follow-ups

B-level (remaining):
- `GET /api/v1/owner/auth/session` rotates the CSRF token. A second tab (or any extra session read) makes the first tab's next save fail with 403.
- Residual (generic, not M3-specific): with the production pool (5 + 5) and the default 40-thread worker pool, more than about 70–80 owner requests in flight at the same instant in one process can still hit 30s `QueuePool` timeouts. Sync endpoints validate their responses in the worker threadpool while still holding their DB connection, so when every worker thread is waiting on the pool, the requests that hold connections can't finish. Up to 70 concurrent requests completed with no errors; 80 gave 4 timeouts. Options (a product/ops decision): size pool + overflow to at least the worker-thread limit, cap concurrent requests per process, or release sessions before serialization.
- Illustrations are placeholders, not photos; 44 archetypes have no art yet.
- The hero can't use starter art in the published design (hero requires tenant media); the demo hero exists in the preview only.
- Uploads replaced by a starter keep counting until the owner deletes them ("Delete unused photo"). No automatic deletion.
- Fulfilment, hostname and payments are activation-only for prospects.
- The admin shell still shows the current business's storefront header (e.g. "The Guest House") above the operations nav.
- Two backend tests are timezone-dependent without `PGTZ=UTC` (pre-existing).
- `test_owner_category_management` depends on test order (pre-existing).
- The frontend bundle has a chunk larger than 500 kB (warning).

C-level (future): a licensed photo pack, hero starter art, per-category collections, automatic media cleanup policies, a CDN for starter media, and a product-row overflow menu on desktop.

## Verification (local, after the pool fix)

- **Backend.** `PGTZ=UTC python -m pytest` → **408 passed** (baseline 386; 400 before the pool fix, plus 8 new pool tests). Without `PGTZ` → 406 passed and 2 failed. Those are the same two pre-existing timezone-format tests that fail at baseline (`test_orders_api::test_clover_checkout_is_idempotent_and_webhook_state_is_monotonic`, `test_owner_orders::test_paid_order_moves_directly_to_completed_and_history`).
- **Tenant isolation / security subset.** `test_tenant_*`, `test_v1_platform_isolation`, `test_jds_auth`, `test_checkout_authorization`, the funnel, starter and pool tests → **138 passed**. The existing isolation test files are unchanged from the base commit.
- **Frontend.** `npm run test:frontend` → **427/427**. `npm run build` passes, with the known >500 kB chunk warning.
- **Migrations.** None added. There is a single alembic head, `20260910_33`, and the test fixtures migrate to head.
- **Manual E2E** (Playwright against local HTTPS vite + uvicorn with the fix + Postgres 17). All 28 spec steps plus the cross-tenant check pass at **375px (29/29)** and **1280px (29/29)**. Email verification is stubbed by local auto-verify. The order-API lockout for prospects is covered by backend tests; the UI and status API were exercised live.
- **Bursts after the fix:**
  - Through the browser and vite proxy: 40, 120 and 300 concurrent owner requests, all 200.
  - In-process at the production pool settings: 25 to 70 concurrent requests, all 200.
  - The backend log for the E2E and burst runs contains **0** `QueuePool`/`TimeoutError` lines and **0** HTTP 500s.
