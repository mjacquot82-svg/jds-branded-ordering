import assert from "node:assert/strict";
import test from "node:test";

import {
  calculateTaxCents,
  formatTaxLabel,
  getOrderPricing,
} from "../../src/services/orderPricing.js";

test("order pricing applies the catalog tax rate with half-up cent rounding", () => {
  const pricing = { taxName: "HST", taxRateMillionths: 1_300_000 };

  assert.equal(calculateTaxCents(1620, pricing.taxRateMillionths), 211);
  assert.deepEqual(getOrderPricing(1620, pricing), {
    subtotalCents: 1620,
    taxCents: 211,
    totalCents: 1831,
  });
  assert.equal(formatTaxLabel(pricing), "HST (13%)");
});

test("order pricing tolerates a menu that is still loading (cart opened directly)", () => {
  assert.deepEqual(getOrderPricing(450, undefined), { subtotalCents: 450, taxCents: 0, totalCents: 450 });
  assert.equal(formatTaxLabel(undefined), "Tax");
  assert.equal(formatTaxLabel({ taxName: "HST", taxRateMillionths: 1_300_000, taxRatePercent: 13 }), "HST (13%)");
});
