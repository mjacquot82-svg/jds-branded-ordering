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
