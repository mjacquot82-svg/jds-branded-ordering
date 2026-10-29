import test from "node:test";
import assert from "node:assert/strict";
import { asapIsLater, describePickupTime, pickupSummaryText } from "../../src/services/pickupWording.js";

const tz = "America/Toronto";
const now = new Date("2026-10-29T22:40:00Z"); // 6:40 PM in Toronto

test("ASAP that resolves to the next morning says tomorrow with the time", () => {
  assert.equal(pickupSummaryText("2026-10-30T11:00:00Z", tz, now), "Ready tomorrow at 7:00 AM");
  assert.equal(asapIsLater("2026-10-30T11:00:00Z", now), true);
});

test("same-day pickup says today; later days name the day", () => {
  assert.equal(describePickupTime("2026-10-29T22:55:00Z", tz, now), "today at 6:55 PM");
  assert.equal(asapIsLater("2026-10-29T22:55:00Z", now), false);
  assert.equal(describePickupTime("2026-11-01T13:00:00Z", tz, now), "Sun, Nov 1 at 8:00 AM");
});

test("cart shows the resolved ASAP time and the owner can stage pay-at-pickup orders", async () => {
  const { readFile } = await import("node:fs/promises");
  const cart = await readFile(new URL("../../src/pages/CartPage.jsx", import.meta.url), "utf8");
  assert.match(cart, /ASAP means the next opening/);
  assert.match(cart, /pickupSummaryText\(selectedPickup\.requested_pickup_at/);
  const orders = await readFile(new URL("../../src/admin/OrdersPage.jsx", import.meta.url), "utf8");
  assert.match(orders, /new: \["Start Preparing", "preparing"\]/);
  assert.match(orders, /preparing: \["Mark Ready", "ready"\]/);
});
