import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildSchedulingLines,
  fetchSchedulingOptions,
  resolveSchedulingSelection,
} from "../../src/services/schedulingApi.js";

const cartPageSource = await readFile(new URL("../../src/pages/CartPage.jsx", import.meta.url), "utf8");
const checkoutOrderSource = await readFile(new URL("../../src/services/checkoutOrder.js", import.meta.url), "utf8");

const schedule = {
  ordering_available: true,
  minimum_lead_time_minutes: 15,
  pickup_interval_minutes: 5,
  maximum_advance_days: 14,
  earliest_pickup_at: "2026-08-04T12:15:00-04:00",
  quick_pickup_options: [
    { key: "asap", label: "ASAP", preference_minutes: null, requested_pickup_at: "2026-08-04T12:15:00-04:00" },
    { key: "preference-20", label: "20 min", preference_minutes: 20, requested_pickup_at: "2026-08-04T12:20:00-04:00" },
  ],
  custom_pickup_at: null,
};

test("backend ASAP is selected by default and its exact timestamp is preserved", () => {
  assert.deepEqual(resolveSchedulingSelection(schedule), schedule.quick_pickup_options[0]);
  assert.equal(
    resolveSchedulingSelection(schedule).requested_pickup_at,
    "2026-08-04T12:15:00-04:00"
  );
});

test("saved pickup preferences match backend options and otherwise fall back to ASAP", () => {
  assert.deepEqual(
    resolveSchedulingSelection(schedule, { type: "preference", minutes: 20 }),
    schedule.quick_pickup_options[1]
  );
  assert.deepEqual(
    resolveSchedulingSelection(schedule, { type: "preference", minutes: 10 }),
    schedule.quick_pickup_options[0]
  );
});

test("ordering unavailable has no selectable pickup", () => {
  assert.equal(
    resolveSchedulingSelection({ ...schedule, ordering_available: false }, { type: "asap" }),
    null
  );
  assert.match(cartPageSource, /!schedule\?\.ordering_available/);
  assert.match(cartPageSource, /schedule\.unavailable_reason/);
});

test("scheduling requests contain stable cart identifiers and refresh payloads after cart changes", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push([url, JSON.parse(options.body)]);
    return { ok: true, status: 200, json: async () => schedule };
  };
  const first = buildSchedulingLines([{
    resolution: "ready", productBackendId: 4, quantity: 1,
    options: [{ variantId: 8 }],
  }]);
  const changed = buildSchedulingLines([{
    resolution: "ready", productBackendId: 4, quantity: 2,
    options: [{ variantId: 8 }],
  }]);

  await fetchSchedulingOptions({ lines: first }, { fetchImpl });
  await fetchSchedulingOptions({ lines: changed }, { fetchImpl });

  assert.equal(calls[0][0], "/api/v1/scheduling/options");
  assert.deepEqual(calls[0][1].lines, [{ product_id: 4, variant_id: 8, quantity: 1 }]);
  assert.deepEqual(calls[1][1].lines, [{ product_id: 4, variant_id: 8, quantity: 2 }]);
});

test("checkout renders backend options and refreshes after stale pickup rejection", () => {
  assert.match(cartPageSource, /schedule\?\.quick_pickup_options/);
  assert.match(cartPageSource, /requestedPickupAt = selectedPickup\.requested_pickup_at/);
  assert.match(cartPageSource, /error\?\.code === "pickup_invalid"/);
  assert.match(cartPageSource, /await refreshScheduling\(\)/);
});

test("frontend contains no authoritative pickup interval or minute-offset calculation", () => {
  assert.doesNotMatch(checkoutOrderSource, /PICKUP_INTERVAL_MINUTES/);
  assert.doesNotMatch(cartPageSource, /quickPickupOptions/);
  assert.doesNotMatch(cartPageSource, /Date\.now\(\) \+/);
  assert.doesNotMatch(cartPageSource, /step="300"/);
});
