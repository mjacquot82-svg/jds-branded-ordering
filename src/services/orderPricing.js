export const TAX_RATE_SCALE = 10_000_000;

export function calculateTaxCents(subtotalCents, taxRateMillionths) {
  if (!Number.isSafeInteger(subtotalCents) || subtotalCents < 0) {
    throw new Error("Order subtotal is invalid.");
  }
  if (
    !Number.isSafeInteger(taxRateMillionths) ||
    taxRateMillionths < 0 ||
    taxRateMillionths > TAX_RATE_SCALE
  ) {
    throw new Error("Order tax rate is invalid.");
  }
  return Math.floor(
    (subtotalCents * taxRateMillionths + TAX_RATE_SCALE / 2) / TAX_RATE_SCALE
  );
}

export function getOrderPricing(subtotalCents, pricing) {
  const taxCents = calculateTaxCents(
    subtotalCents,
    pricing.taxRateMillionths
  );
  return {
    subtotalCents,
    taxCents,
    totalCents: subtotalCents + taxCents,
  };
}

export function formatTaxLabel(pricing) {
  const percent = pricing.taxRateMillionths / 100_000;
  return `${pricing.taxName} (${percent.toLocaleString("en-US")}%)`;
}
