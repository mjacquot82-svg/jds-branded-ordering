# Manual / pay-at-pickup handling (recommended)

**Status:** Guidance for M1+. Electronic adapters remain the only path that may set `payment_status=paid` with a provider transaction id.

## Rules

1. **Unpaid / manual must NEVER look electronically paid.**  
   Use `payment_status=manual_unpaid` (or `unpaid`) and keep `order.status` out of `paid` unless cash/card-at-counter was recorded by an explicit staff action that does **not** invent a provider txn id.
2. **Do not** call provider checkout, webhooks, or `mark_electronically_paid` for pay-at-pickup.
3. Owner UX should label these orders as **Pay at pickup** / **Unpaid**, never “Paid via Clover/Square/…”.
4. Future staff action (out of M1 scope unless low-risk): `POST /orders/{id}/mark-manual-collected` that sets fulfillment-friendly state + `payment_status=manual_unpaid`→`paid` only with `payment_provider=null` and an audit row — still distinct from electronic `payment_provider_txn_id`.

## M1 stance

M1 does **not** implement pay-at-pickup checkout. The data model reserves `manual_unpaid` so a later small change can land without schema redesign.

## M4 (trial readiness) — implemented

- **Per-shop switch, off by default:** `organization_order_settings` (owner UI: Scheduling page → "Pay at pickup & order alerts", and setup step 6). API `GET/PUT /api/v1/owner/order-settings`.
- **No-show protections (server-enforced):** verified email; at least `pay_at_pickup_min_completed_orders` paid+completed orders at this shop (default 1); total ≤ `pay_at_pickup_max_total_cents` (default $25); not in `pay_at_pickup_blocks`.
- **Customer:** `GET /api/v1/payments/pay-at-pickup/eligibility?total_cents=` (advisory) and `POST /api/v1/payments/orders/{token}/pay-at-pickup` → `status=payment_pending`, `payment_status=manual_unpaid`, no provider, no txn id. Expiry extended to pickup + 12h.
- **Staff:** `POST /api/v1/owner/orders/{id}/mark-paid` (paid at counter: `payment_status=paid`, `payment_provider=null`, audit `order.pay_at_pickup.collected`) and `POST /api/v1/owner/orders/{id}/no-show` (cancel + block customer, audit `order.pay_at_pickup.no_show`). Orders must be marked paid before "Mark Completed".
- **Readiness:** `payment_connected` is satisfied by an electronic provider **or** pay at pickup being on. Connect Clover is shown only when the platform has Clover credentials (`paymentOptions.cloverAvailable`).
- **New-order email alert:** `app/communications/order_alerts.py`, sent after pay-at-pickup confirmation or electronic payment. Needs `JDS_ORDER_ALERT_RESEND_API_KEY` + `JDS_ORDER_ALERT_FROM_EMAIL` and the shop's alert email; otherwise skipped. Failures are logged and never affect the order.
- To clear a no-show block today: delete the row in `pay_at_pickup_blocks` (no UI yet).
