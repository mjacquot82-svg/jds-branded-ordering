const WORDS = /[a-z0-9]+/g;

const STARTER_CATEGORY_LABELS = {
  coffee: "Coffee",
  "tea-specialty-drinks": "Tea & Specialty Drinks",
  "cold-drinks": "Cold Drinks",
  breakfast: "Breakfast",
  bakery: "Bakery",
  "sandwiches-wraps": "Sandwiches & Wraps",
  "lunch-savoury": "Lunch & Savoury",
  "soup-salad": "Soup & Salad",
  desserts: "Desserts",
  "packaged-retail": "Packaged & Retail",
};

export function starterCategoryLabel(category) {
  return STARTER_CATEGORY_LABELS[category] || String(category || "").replaceAll("-", " ");
}

export function productWords(value) {
  return new Set(String(value || "").toLowerCase().match(WORDS) || []);
}

export function starterMatchScore(asset, productName) {
  const words = productWords(productName);
  if (!words.size) return 0;
  const keyWords = productWords(`${asset.key} ${asset.name}`);
  const tagWords = productWords((asset.tags || []).join(" "));
  let score = 0;
  for (const word of words) {
    if (keyWords.has(word)) score += 10;
    if (tagWords.has(word)) score += 4;
  }
  return score;
}

export function suggestedStarterMedia(assets, productName) {
  return assets.map((asset) => ({ asset, score: starterMatchScore(asset, productName) }))
    .filter(({ score }) => score > 0)
    .sort((left, right) => right.score - left.score || left.asset.sortOrder - right.asset.sortOrder)
    .map(({ asset }) => asset);
}

export function filterStarterMedia(assets, { category = "all", query = "" } = {}) {
  const terms = [...productWords(query)];
  return assets.filter((asset) => {
    if (category !== "all" && asset.category !== category) return false;
    if (!terms.length) return true;
    const haystack = productWords(`${asset.name} ${asset.key} ${(asset.tags || []).join(" ")}`);
    return terms.every((term) => haystack.has(term));
  });
}

export function starterPreviewUrl(reference) {
  const match = /^starter:([a-z0-9-]+)\/([a-z0-9-]+)@(\d+)$/.exec(reference || "");
  return match ? `/api/v1/storefront/starter-media/${match[1]}/${match[2]}?version=${match[3]}` : reference || "";
}
