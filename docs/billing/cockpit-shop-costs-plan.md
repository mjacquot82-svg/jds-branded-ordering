# Plan: per-shop cost vs revenue in JDS Owner Cockpit

Nothing in the Cockpit repo (mjacquot82-svg/jds-owner-cockpit) is changed yet. This is the plan for it.

## 1. Data the ordering app now provides
`GET https://jds-beta-api.canner.app/api/v1/platform/cockpit/feed?period=YYYY-MM`
with header `Authorization: Bearer <JDS_COCKPIT_FEED_TOKEN>` (feed is off/404 until that token is set).
Read-only, no customer names/emails/phones/cards. One row per shop:

| field | meaning |
|---|---|
| organizationId, slug, name, lifecycleStatus | shop identity |
| package, extraLocations, billingExempt, billingStatus | plan state |
| listPriceCents | package + extra locations at list price |
| expectedRevenueCents | what JDS should bill this month (0 if billing off or shop exempt) |
| billedCents / paidCents / failedCents | real platform charges this month (from Square webhooks) |
| ordersPlaced, ordersPaid, orderSalesCents | shop activity (sales go to the shop, not JDS) |
| emailsSent | receipts, refund emails, owner alerts, billing emails sent this month |
| textsSent | 0 until texts are built |
| mediaFiles, storageBytes | uploaded images (current) |
| activeStaff, products, customers | size of the shop |

Plus `totals` across shops. Optional push: set `JDS_COCKPIT_WEBHOOK_URL` and each paid/failed charge is POSTed as
`{type: "jds.billing.payment_paid"|"jds.billing.payment_failed", id, organizationId, amountCents, currency, package, period, occurredAt}`
with header `X-JDS-Signature` = hex HMAC-SHA256(feed token, raw body). Cockpit must verify it and de-duplicate on `id`.

## 2. Cockpit side (to build later)
1. **Link shops to clients**: add `ordering_org_id` to Cockpit's client (or project) record; match once by slug/name.
2. **Pull the feed**: a daily job (and a "Refresh" button) calls the feed for the current and previous month and
   upserts a `shop_usage_monthly` table (client_id, period, all fields above). Store the token as a Cockpit secret.
3. **Shared bills**: Cockpit already tracks your own costs. Tag the shared ones with a driver:
   - Canner (API + web + database) → split by `ordersPlaced` (fallback: even split)
   - Supabase (auth) → split by `customers + activeStaff + 1`
   - Resend → split by `emailsSent`
   - Twilio (later) → `textsSent` (direct, not shared)
   - Storage-heavy items → `storageBytes`
   - Anything else (domain, UptimeRobot, Square fees on JDS billing) → even split across active shops
   Rule: `shop_share = bill × shop_driver / sum(all shops' driver)`; if every shop is 0, split evenly. Keep a minimum
   floor per active shop (e.g. even split of 30% of each bill) so tiny shops still carry some fixed cost.
4. **Revenue**: use `paidCents` once billing is on; before that show `listPriceCents` greyed as "would be".
5. **View**: per shop per month: Revenue | Allocated cost (with a breakdown per bill) | Margin | Margin %. Totals row,
   red highlight when margin < 0, and a trend line over months.
6. **Payments ledger**: optionally receive the webhook events into Cockpit's invoices/payments so the client's
   "paid" status updates automatically (don't also bill them from Cockpit to avoid billing in two places).
