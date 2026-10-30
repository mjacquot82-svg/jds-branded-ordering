# JDS platform billing (shops pay JDS)

Everything here is **OFF by default**. With `JDS_BILLING_ENABLED` unset/false:
nothing is charged, no billing emails are sent, nothing is paused, and every feature stays unlocked (same as today).

Even when switched on, shops with `billing_exempt = true` are never charged, gated or paused.
**Every shop that existed when the migration ran (all beta shops) is marked exempt.** New sign-ups are not exempt.
Change it per shop with `PUT /api/v1/platform/admin/organizations/{id}/billing-exempt {"exempt": false}` (needs the `platform.organizations.write` grant).

## How it works
- **Card on file + subscription** – the owner adds a card in Dashboard › Billing (Square Web Payments card form).
  The backend creates a Square customer + card + subscription in **JDS's own Square account** (`JDS_BILLING_SQUARE_*`),
  never the shop's connected Square account. Price = package price + $75 × extra locations (sent as `price_override_money`).
- **Plan changes** – `PUT /owner/billing/package`. Square swaps the plan at the start of the next billing period; the new
  price is set on the subscription. Our record keeps the old package until the next paid invoice, then switches.
- **Failed payment** – Square webhook `invoice.scheduled_charge_failed` → status `past_due`, a 7-day grace period
  (`JDS_BILLING_GRACE_DAYS`) and a reminder email to the owner (Resend, same sender as receipts). The daily sweep
  re-sends a reminder every 2 days (max 4) and, when grace ends, pauses online ordering (new orders get
  "Online ordering for this shop is paused"). Webhook `invoice.payment_made` → `active`, ordering resumes, "back on" email.
  No new-order emails are added.
- **Feature gating** (only when on and not exempt): Starter = base; Plus adds loyalty, announcements/push,
  customer list, staff PINs (creating new staff); Pro adds texts, reports, own domain, priority support
  (the flags exist; those features aren't built yet). Existing staff logins keep working after a downgrade.

## Endpoints
| | |
|---|---|
| `GET /api/v1/owner/billing` | owner billing view (package, next bill, card brand/last 4, status, freeDuringBeta) |
| `POST /api/v1/owner/billing/card` | `{sourceId, package?}` – save card, start subscription |
| `PUT /api/v1/owner/billing/package` | `{package, extraLocations?}` – takes effect next bill |
| `POST /api/v1/billing/square/webhook` | Square billing webhook (signature-verified) |
| `GET /api/v1/platform/admin/billing` | who's paid/behind, monthly recurring total |
| `POST /api/v1/platform/admin/billing/sweep` | run reminders/pausing now |
| `GET /api/v1/platform/cockpit/feed?period=YYYY-MM` | Cockpit feed (Bearer `JDS_COCKPIT_FEED_TOKEN`) |

## New settings (backend, jds-beta-api)
| Variable | Secret? | Value |
|---|---|---|
| `JDS_BILLING_ENABLED` | no | `false` (master switch) |
| `JDS_BILLING_SQUARE_ENVIRONMENT` | no | `sandbox` until you go live, then `production` |
| `JDS_BILLING_SQUARE_ACCESS_TOKEN` | **yes** | access token of the JDS Studio Square account |
| `JDS_BILLING_SQUARE_APPLICATION_ID` | no | application id (for the card form) |
| `JDS_BILLING_SQUARE_LOCATION_ID` | no | JDS Studio's Square location id |
| `JDS_BILLING_PLAN_VARIATION_STARTER` / `_PLUS` / `_PRO` | no | plan variation ids from Square |
| `JDS_BILLING_WEBHOOK_SIGNATURE_KEY` | **yes** | from the Square webhook subscription |
| `JDS_BILLING_WEBHOOK_URL` | no | `https://jds-beta-api.canner.app/api/v1/billing/square/webhook` |
| `JDS_BILLING_GRACE_DAYS` | no | `7` (default) |
| `JDS_BILLING_EXTRA_LOCATION_CENTS` | no | `7500` (default) |
| `JDS_COCKPIT_FEED_TOKEN` | **yes** | long random string; also used to sign Cockpit hook posts |
| `JDS_COCKPIT_WEBHOOK_URL` | no | optional, Cockpit URL to receive payment events |

Billing emails use the existing `JDS_ORDER_ALERT_RESEND_API_KEY` / `JDS_ORDER_ALERT_FROM_EMAIL`.

## Steps to turn billing on (sandbox first)
1. Use JDS Studio's **own** Square account – a separate app from "JDS Ordering"'s shop OAuth, and never Tee & Co's or
   the "Wellington Apparel Co." app. In the Square Developer dashboard, sandbox: copy the access token, application id, location id.
2. Create a subscription plan "JDS Coffee Ordering" with three monthly variations in CAD: Starter $150, Plus $225, Pro $300
   (Catalog › Subscription plans, or the Catalog API `SUBSCRIPTION_PLAN` + `SUBSCRIPTION_PLAN_VARIATION`). Copy the 3 variation ids.
3. Add a webhook subscription to `…/api/v1/billing/square/webhook` for `invoice.payment_made`,
   `invoice.scheduled_charge_failed`, `subscription.updated`. Copy its signature key.
4. Set the variables above on jds-beta-api (leave `JDS_BILLING_ENABLED=false` while setting up).
5. Add a daily Canner cron job: `.venv/bin/python -m app.billing.sweep` (does nothing while off).
6. Flip `JDS_BILLING_ENABLED=true`. Beta shops stay free (exempt). Test with a non-exempt test shop and Square's sandbox
   test card; then for real: swap to production values and `JDS_BILLING_SQUARE_ENVIRONMENT=production`.
7. Give beta shops their 30 days' notice, then un-exempt them one by one.

## Known limits
- If a card fails, Square doesn't automatically re-charge a new card for the unpaid invoice. The owner pays the
  Square invoice email (or you charge it in Square Dashboard) – that fires `invoice.payment_made` and ordering resumes.
- Plan-change proration isn't done: the new price starts next bill.
- Cancelling a subscription from the app isn't built (cancel in Square Dashboard; `subscription.updated` records it).
- Clover shops are billed the same way (billing uses JDS's Square, not the shop's payment provider).
