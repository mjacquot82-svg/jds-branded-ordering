const normalizedMoneyCents = (value) => {
  const amount = Number(value);
  return Number.isFinite(amount) ? Math.round(amount * 100) : null;
};

const sortedUnique = (values = []) => [...new Set(values.filter(Boolean))].sort();

export function productDraftSignature(draft, defaultCategory = "") {
  if (!draft) return "";
  return JSON.stringify({
    name: (draft.name ?? "").trim(),
    description: (draft.description ?? "").trim(),
    price_cents: normalizedMoneyCents(draft.price),
    category: draft.category || defaultCategory,
    image: draft.image || "",
    available: draft.available !== false,
    published: draft.published !== false,
    featured: Boolean(draft.featured),
    lunch_special: Boolean(draft.lunchSpecial),
    variants: (draft.variants || []).map((variant, index) => ({
      key: variant.key || "",
      name: (variant.name ?? "").trim(),
      price_cents: normalizedMoneyCents(variant.price),
      active: variant.active !== false,
      sort_order: index,
    })),
    modifier_group_ids: sortedUnique(draft.modifierGroupIds),
  });
}

export function isProductDraftDirty(draft, savedDraft, defaultCategory = "") {
  return Boolean(draft && savedDraft && productDraftSignature(draft, defaultCategory) !== productDraftSignature(savedDraft, defaultCategory));
}
