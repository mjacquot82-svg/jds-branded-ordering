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

## Guest House storefront

Verified unchanged. Screenshots of `/`, `/menu`, `/cart` and `/account/sign-in` at 375px and 1280px from the base commit and from this branch are **pixel-identical**, and the title is still "The Guest House · Order online". All new CSS is scoped to owner/preview classes (`.full-design-preview`, `.layout-product-grid`, `.demo-hero*`, `.category-management-list`, `.product-row-actions`, `.product-image-save-hint`, wizard classes).

## Known limitations / follow-ups

B-level (remaining):
- `GET /api/v1/owner/auth/session` rotates the CSRF token. A second tab (or any extra session read) makes the first tab's next save fail with 403.
- Pre-existing DB pool starvation risk. `authenticated_owner_tenant` is an `async` dependency that opens a blocking DB session on the event loop, while the request already holds auth and catalog sessions (pool 5+5). Under a burst of owner requests this was seen locally as 30s `QueuePool limit` timeouts (7 occurrences across the local E2E runs). Recommended fix: make the dependency sync and reuse the request session.
- Illustrations are placeholders, not photos; 44 archetypes have no art yet.
- The hero can't use starter art in the published design (hero requires tenant media); the demo hero exists in the preview only.
- Uploads replaced by a starter keep counting until the owner deletes them ("Delete unused photo"). No automatic deletion.
- Fulfilment, hostname and payments are activation-only for prospects.
- The admin shell still shows the current business's storefront header (e.g. "The Guest House") above the operations nav.
- Two backend tests are timezone-dependent without `PGTZ=UTC` (pre-existing).
- `test_owner_category_management` depends on test order (pre-existing).
- The frontend bundle has a chunk larger than 500 kB (warning).

C-level (future): a licensed photo pack, hero starter art, per-category collections, automatic media cleanup policies, a CDN for starter media, and a product-row overflow menu on desktop.

## Verification (local)

- Backend: `PGTZ=UTC python -m pytest` → **400 passed** (the baseline was 386). Without `PGTZ` → 398 passed and 2 failed. Those are the same two pre-existing timezone-format tests that fail at baseline (`test_orders_api::test_clover_checkout_is_idempotent_and_webhook_state_is_monotonic`, `test_owner_orders::test_paid_order_moves_directly_to_completed_and_history`).
- Frontend: `npm run test:frontend` → **427/427** (baseline 416 before M3's newest tests). `npm run build` passes, with the known >500 kB chunk warning.
- Migrations: none added; a single alembic head, `20260910_33`.
- Manual E2E (Playwright against local HTTPS vite + uvicorn + Postgres 17): all 28 spec steps plus the cross-tenant check pass at **375px (29/29)** and **1280px (29/29)**. Email verification is stubbed by local auto-verify. The order-API lockout for prospects is covered by backend tests; the UI and status API were exercised live.
