import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("orders allow capable Staff to complete orders while gating financial and administrative controls", async () => {
  const page = await readFile(new URL("../../src/admin/OrdersPage.jsx", import.meta.url), "utf8");
  assert.match(page, /hasPermission\(session, "orders\.fulfill"\)/);
  assert.match(page, /showFinancials=\{administrator\}/);
  assert.match(page, /administrator && order\.payment_status/);
  assert.match(page, /administrator \? <strong>\{money\(order\.total_cents/);
  assert.match(page, /Mark Completed/);
  assert.match(page, /Return to Active/);
  assert.match(page, /history && canFulfill/);
  assert.match(page, /canFulfill && order\.payment_status === "paid"/);
  assert.doesNotMatch(page, /next\[1\] !== "completed"/);
});

test("dashboard and Communications provide a capability-scoped announcement view", async () => {
  const dashboard = await readFile(new URL("../../src/admin/AdminDashboard.jsx", import.meta.url), "utf8");
  const communications = await readFile(new URL("../../src/admin/CommunicationsPage.jsx", import.meta.url), "utf8");
  assert.match(dashboard, /Active paid orders/);
  assert.match(dashboard, /Sold-out products/);
  assert.match(dashboard, /Online ordering/);
  assert.match(dashboard, /Communication warnings/);
  assert.match(dashboard, /communications\.summary\.actionable_warnings/);
  assert.doesNotMatch(dashboard, /communications\.summary\.failed/);
  assert.match(dashboard, /administrator \? <Link className="metric-card metric-card-link" to="\/admin\/orders"><span>Today’s paid pickups/);
  assert.match(communications, /Lunch Special announcement/);
  assert.match(communications, /owner \? <section className="communications-panel" aria-labelledby="general-announcement-heading"/);
  assert.match(communications, /Push notifications are not connected yet/);
  assert.match(communications, /Recent announcement activity/);
  assert.doesNotMatch(communications, /Order notifications|Notification templates|Postmark|Twilio|Password reset|Account verification/);
});

test("the shared Operations navigation is rendered from session capabilities", async () => {
  const boundary = await readFile(new URL("../../src/auth/RequireOwner.jsx", import.meta.url), "utf8");
  const layout = await readFile(new URL("../../src/layouts/AppLayout.jsx", import.meta.url), "utf8");
  assert.match(boundary, /operationsLinks\(session\)\.map/);
  assert.match(boundary, /Operations Portal navigation/);
  assert.doesNotMatch(layout, /\/admin\/communications/);
});

test("Products exposes narrow Staff Lunch Special controls separately from Quick Edit", async () => {
  const page = await readFile(new URL("../../src/admin/ProductsPage.jsx", import.meta.url), "utf8");
  assert.match(page, /canManageLunchSpecial\(session\)/);
  assert.match(page, /Set as Lunch Special/);
  assert.match(page, /Clear Lunch Special/);
  assert.match(page, /canManageSpecial \? <button/);
  assert.match(page, /canEdit \? <section className="product-editor-panel"/);
});
