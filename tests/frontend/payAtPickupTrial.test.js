import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  choosePayAtPickup,
  fetchPayAtPickupEligibility,
  payAtPickupUnavailableMessage,
} from "../../src/services/paymentService.js";
import { markOwnerOrderNoShow, markOwnerOrderPaidAtCounter } from "../../src/services/ownerOrdersApi.js";
import { buildOrderSettingsPayload } from "../../src/services/ownerOrderSettingsApi.js";

const source = (path) => readFile(new URL(path, import.meta.url), "utf8");
const ok = (body) => ({ ok: true, status: 200, json: async () => body });

test("eligibility asks the server with the order total and fails closed", async () => {
  const value = await fetchPayAtPickupEligibility(1999, {
    apiBaseUrl: "https://api.example.test",
    fetchImpl: async (url, init) => {
      assert.equal(url, "https://api.example.test/api/v1/payments/pay-at-pickup/eligibility?total_cents=1999");
      assert.equal(init.credentials, "include");
      return ok({ available: true, max_total_cents: 2500, min_completed_orders: 1, completed_orders: 3 });
    },
  });
  assert.equal(value.available, true);
  assert.deepEqual(await fetchPayAtPickupEligibility(100, { fetchImpl: async () => { throw new Error("down"); } }), { available: false, reason: "unavailable" });
  assert.equal((await fetchPayAtPickupEligibility(100, { fetchImpl: async () => ({ ok: false, status: 403, json: async () => ({}) }) })).available, false);
});

test("choosing pay at pickup posts to the order and never invents a paid state", async () => {
  const result = await choosePayAtPickup("tok en", {
    apiBaseUrl: "",
    fetchImpl: async (url, init) => {
      assert.equal(url, "/api/v1/payments/orders/tok%20en/pay-at-pickup");
      assert.equal(init.method, "POST");
      return ok({ payment_method: "pay_at_pickup", payment_status: "manual_unpaid", order_status: "payment_pending" });
    },
  });
  assert.equal(result.payment_status, "manual_unpaid");
});

test("customers see plain reasons when pay at pickup is unavailable", () => {
  assert.match(payAtPickupUnavailableMessage({ reason: "not_enough_completed_orders", min_completed_orders: 1 }), /after 1 completed order\./);
  assert.match(payAtPickupUnavailableMessage({ reason: "order_total_too_high", max_total_cents: 2500 }), /\$25\.00/);
  assert.match(payAtPickupUnavailableMessage({ reason: "blocked_after_no_show" }), /turned off/);
  assert.equal(payAtPickupUnavailableMessage({ reason: "not_offered" }), "");
});

test("staff mark-paid and no-show send the expected version with CSRF", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => { calls.push([url, init]); return ok({ id: 7 }); };
  await markOwnerOrderPaidAtCounter(7, 3, "csrf-1", { apiBaseUrl: "", fetchImpl });
  await markOwnerOrderNoShow(7, 4, "csrf-1", { apiBaseUrl: "", fetchImpl });
  assert.equal(calls[0][0], "/api/v1/owner/orders/7/mark-paid");
  assert.equal(calls[1][0], "/api/v1/owner/orders/7/no-show");
  assert.equal(calls[0][1].headers["X-CSRF-Token"], "csrf-1");
  assert.deepEqual(JSON.parse(calls[1][1].body), { expected_version: 4 });
});

test("order settings payload clamps values and defaults to safe limits", () => {
  assert.deepEqual(buildOrderSettingsPayload({ pay_at_pickup_enabled: true, pay_at_pickup_min_completed_orders: "2", max_total_dollars: "30", new_order_alert_email: " a@b.co " }), {
    pay_at_pickup_enabled: true, pay_at_pickup_min_completed_orders: 2, pay_at_pickup_max_total_cents: 3000, new_order_alert_email: "a@b.co",
  });
  assert.equal(buildOrderSettingsPayload({ max_total_dollars: "abc" }).pay_at_pickup_max_total_cents, 2500);
  assert.equal(buildOrderSettingsPayload({ max_total_dollars: "0" }).pay_at_pickup_max_total_cents, 100);
  assert.equal(buildOrderSettingsPayload({}).new_order_alert_email, null);
});

test("Connect Clover only shows when Clover is configured; go-live links reach setup", async () => {
  const wizard = await source("../../src/setup/SetupWizard.jsx");
  const dashboard = await source("../../src/admin/AdminDashboard.jsx");
  const requireOwner = await source("../../src/auth/RequireOwner.jsx");
  assert.match(wizard, /cloverAvailable&&!ready\?/);
  assert.doesNotMatch(wizard, /:<a className="primary-button" href=\{getCloverConnectUrl\(\)\}>Connect Clover/);
  assert.match(dashboard, /canManageIntegrations && !cloverHidden/);
  assert.match(requireOwner, /\(go-live\|launch\)/);
  assert.match(requireOwner, /to="\/setup\/launch"/);
});

test("cart and staff screens expose pay at pickup clearly", async () => {
  const cart = await source("../../src/pages/CartPage.jsx");
  const orders = await source("../../src/admin/OrdersPage.jsx");
  assert.match(cart, /How would you like to pay\?/);
  assert.match(cart, /Pay at the counter when you pick up your order\./);
  assert.match(orders, /Mark as paid/);
  assert.match(orders, /No-show/);
  assert.match(orders, /Pay at pickup · not paid yet/);
});

test("Guest House photo stays Guest House only; pilot build gets neutral title", async () => {
  const css = await source("../../src/style.css");
  const script = await source("../../scripts/write-staging-redirects.js");
  assert.match(css, /html\[data-tenant-slug\]:not\(\[data-tenant-slug="the-guest-house"\]\) \.ordering-top-card/);
  assert.match(script, /<title>Order online<\/title>/);
  const html = await source("../../index.html");
  assert.match(html, /<title>Ladel's Wellness Café<\/title>/); // live default build unchanged
});
