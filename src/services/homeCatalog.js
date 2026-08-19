const CRAFTED_DRINK_CATEGORIES = new Set([
  "coffee",
  "espresso",
  "tea",
  "iced-drinks",
]);

export function getHomeCategoryById(categories, categoryId) {
  return categories.find((category) => category.id === categoryId);
}

export function createQuickOrderItems(products, { featuredLimit = 4, limit = 6, personalizedProductIds = [] } = {}) {
  const availableProducts = products.filter((product) => product.available);
  const productsByBackendId = new Map(
    availableProducts.map((product) => [product.backendId, product])
  );
  const seenPersonalizedIds = new Set();
  const personalized = personalizedProductIds
    .map((productId) => productsByBackendId.get(String(productId)))
    .filter((product) => {
      if (!product || seenPersonalizedIds.has(product.id)) return false;
      seenPersonalizedIds.add(product.id);
      return true;
    });
  const personalizedIds = new Set(personalized.map((product) => product.id));
  const prioritized = availableProducts
    .filter((product) => product.featured && !personalizedIds.has(product.id))
    .slice(0, featuredLimit);
  const prioritizedIds = new Set([
    ...personalizedIds,
    ...prioritized.map((product) => product.id),
  ]);

  return [
    ...personalized,
    ...prioritized,
    ...availableProducts.filter((product) => !prioritizedIds.has(product.id)),
  ].slice(0, limit);
}

export function createHomeCatalogView(status, catalog) {
  const categories = catalog?.categories || [];
  const products = catalog?.products || [];
  const availableProducts = products.filter((product) => product.available);

  return {
    status,
    categories,
    popularItems: availableProducts
      .filter((product) => product.featured)
      .slice(0, 4),
    lunchSpecial:
      availableProducts.find((product) => product.lunchSpecial) || null,
    coffeeCount: availableProducts.filter((product) =>
      CRAFTED_DRINK_CATEGORIES.has(product.category)
    ).length,
  };
}
