export function businessNameSlug(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[’']/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63)
    .replace(/-+$/g, "");
}

export function initialBusinessDetails(profile, storefront) {
  const suggestedSlug = businessNameSlug(profile.display_name);
  const useSuggestion = Boolean(storefront.slugIsSuggestion && suggestedSlug.length >= 3);
  return { profile, slug: useSuggestion ? suggestedSlug : storefront.slug, slugCustomized: !useSuggestion };
}

export function updateBusinessName(state, displayName) {
  return {
    ...state,
    profile: { ...state.profile, display_name: displayName },
    slug: state.slugCustomized ? state.slug : businessNameSlug(displayName),
  };
}

export function customizeBusinessSlug(state, value) {
  return { ...state, slug: businessNameSlug(value), slugCustomized: true };
}

export function merchantAppAddress(slug, suffix) {
  return `${slug}${suffix || ""}`;
}
