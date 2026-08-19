export function dollarsToCents(value) {
  const normalized = String(value).trim();
  if (!/^\d+(?:\.\d{0,2})?$/.test(normalized)) return null;
  const [whole, fraction = ""] = normalized.split(".");
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return Number.isSafeInteger(cents) ? cents : null;
}

export function toOwnerCustomizationWrite(customization, naturalOrder = 0) {
  const single = customization.selectionType === "single";
  const minSelections = single ? (customization.required ? 1 : 0) : Number(customization.minSelections);
  const maxSelections = single && !customization.allowQuantity ? 1 : Number(customization.maxSelections);
  return {
    groupId: customization.backendId,
    group: {
      name: customization.name.trim(), description: customization.description?.trim() || "",
      selection_type: customization.selectionType, required: minSelections > 0,
      min_selections: minSelections, max_selections: maxSelections,
      allow_quantity: Boolean(customization.allowQuantity),
      active: customization.active !== false,
      sort_order: Number.isFinite(Number(customization.sortOrder))
        ? Number(customization.sortOrder)
        : naturalOrder,
    },
    choices: customization.choices.map((choice, index) => ({
      clientId: choice.draftId,
      optionId: choice.backendId,
      payload: {
        name: choice.name.trim(), price_adjustment_cents: Number(choice.priceAdjustmentCents),
        active: choice.active !== false, sort_order: index,
      },
    })),
  };
}
