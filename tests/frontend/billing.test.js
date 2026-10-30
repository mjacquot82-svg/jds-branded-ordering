import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { billingLines, billingStatusLabel, money } from "../../src/services/billingApi.js";

test("billing off or exempt shows only the free-during-beta line", () => {
  assert.deepEqual(billingLines({ freeDuringBeta: true, monthlyAmountCents: 22500 }), ["Free during the beta — you won't be charged."]);
});

test("billing on shows package, price, next bill, card and failed-payment warning", () => {
  const lines = billingLines({ freeDuringBeta: false, packageName: "Plus", monthlyAmountCents: 30000, extraLocations: 1, pendingPackage: "pro",
    nextBillOn: "2026-12-01", card: { brand: "VISA", last4: "1111" }, status: "past_due", graceEndsAt: "2026-12-08T12:00:00Z", orderingPaused: false });
  assert.match(lines[0], /^Plus: \$300\.00\/month CAD \(includes 1 extra location\)$/);
  assert.ok(lines.some((l) => l === "Changing to Pro on your next bill."));
  assert.ok(lines.some((l) => /^Next bill: December 1, 2026$/.test(l)));
  assert.ok(lines.includes("Card: VISA ending in 1111"));
  assert.ok(lines.some((l) => /didn't go through/.test(l)));
  assert.equal(money(1234567), "$12,345.67");
  assert.equal(billingStatusLabel("past_due"), "Payment failed");
});

test("dashboard and platform admin include the billing panels", async () => {
  const dashboard = await readFile(new URL("../../src/admin/AdminDashboard.jsx", import.meta.url), "utf8");
  const admin = await readFile(new URL("../../src/admin/PlatformAdminPage.jsx", import.meta.url), "utf8");
  assert.match(dashboard, /<BillingCard canChange/);
  assert.match(admin, /<PlatformBillingPanel \/>/);
  const card = await readFile(new URL("../../src/admin/BillingCard.jsx", import.meta.url), "utf8");
  assert.match(card, /freeDuringBeta/);
});
