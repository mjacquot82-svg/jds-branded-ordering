// Tax rates use a 10,000,000 = 100% scale (1,300,000 = 13%).
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
  // The menu may still be loading (e.g. /cart opened directly); show no tax yet
  // instead of crashing. Real orders are always priced by the server.
  if (!pricing || !Number.isSafeInteger(pricing.taxRateMillionths)) {
    return { subtotalCents, taxCents: 0, totalCents: subtotalCents };
  }
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
  if (!pricing) return "Tax";
  const percent = Number.isFinite(pricing.taxRatePercent)
    ? pricing.taxRatePercent
    : pricing.taxRateMillionths / 100_000;
  return `${pricing.taxName} (${percent.toLocaleString("en-US")}%)`;
}
