# Manual beta shop onboarding (no self-serve)

Use placeholders only; never paste real customer data into tickets or chat.

1. **Gate signup.** Set `JDS_DEMO_INVITE_CODE` to a random value on the API. Only people with the link can sign up.
2. **Send the shop owner** `https://<web-host>/build?invite=<code>` (one shop at a time). They sign up and verify
   their email; this creates their own organization (tenant), separate from every other shop.
   Alternative for a shop that can't self-signup: `python -m app.jds_auth.bootstrap_owner --email <owner@shop>
   --application-name "<Shop> Ordering" --organization-name "<Shop>"` (sends an owner invite).
3. **Platform admin → Organizations → Demo prospects → Promote to live** (`src/admin/PlatformAdminPage.jsx`).
4. **Shop setup call (30 min):** menu + prices, photos, hours, Design Studio branding, Order settings →
   enable **Pay at pickup** (`src/admin/OrderSettingsPanel.jsx`), add staff.
5. **Isolation check before go-live:** sign in as shop A, confirm none of shop B's menu/orders/customers appear;
   place one test order on each storefront and confirm it shows only in that shop's queue.
6. **Tell the shop:** beta terms (docs/drafts), the "Report a problem" link, and that payment is collected at
   the counter — mark orders "Paid at counter" or "No-show" in Orders.
7. **Record** shop name, owner email, go-live date and free-until date in Marc's own tracker (not in the repo).

Offboarding: Platform admin → set organization to suspended/archived; export their data on request first.
