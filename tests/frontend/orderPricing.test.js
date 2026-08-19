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
