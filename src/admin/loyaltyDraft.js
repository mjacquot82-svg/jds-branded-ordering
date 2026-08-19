const sortedIds = (ids = []) => [...new Set(ids)].sort();

export function loyaltyDraftSignature(draft) {
  if (!draft) return "";
  return JSON.stringify({
    name: draft.name ?? "",
    enabled: Boolean(draft.enabled),
    description: draft.description ?? "",
    stamps_required: Number(draft.stamps_required),
    reward_description: draft.reward_description ?? "",
    earning_product_ids: sortedIds(draft.earning_product_ids),
    reward_product_ids: sortedIds(draft.reward_product_ids),
  });
}

export function isLoyaltyDraftDirty(draft, savedDraft) {
  return Boolean(draft && savedDraft && loyaltyDraftSignature(draft) !== loyaltyDraftSignature(savedDraft));
}
