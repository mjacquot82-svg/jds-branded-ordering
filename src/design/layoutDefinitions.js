export const layoutDefinitions = Object.freeze({
  modern: Object.freeze({
    id: "modern",
    name: "Modern",
    personality: "Bold and visual",
    summary: "Large imagery · prominent ordering · quick access",
    hero: "immersive",
    navigation: "mobile-dock",
    categories: "visual-grid",
    productCards: "media-cards",
    quickOrder: "home-rail",
    featured: "hero-followup",
    cart: "floating-status",
    account: "dock",
    homeSections: Object.freeze(["announcement", "hero", "categories", "quickOrder", "featured"]),
  }),
  minimal: Object.freeze({
    id: "minimal",
    name: "Minimal",
    personality: "Clean and refined",
    summary: "Simple navigation · compact menu · focused content",
    hero: "wordmark",
    navigation: "editorial",
    categories: "compact-tabs",
    productCards: "editorial-rows",
    quickOrder: "browse-only",
    featured: "inline",
    cart: "header-link",
    account: "header-link",
    homeSections: Object.freeze(["announcement", "intro", "categories", "featured"]),
  }),
  cozy: Object.freeze({
    id: "cozy",
    name: "Cozy",
    personality: "Warm and welcoming",
    summary: "Café-focused · featured favourites · layered home",
    hero: "framed-photo",
    navigation: "cafe-tabs",
    categories: "tile-grid",
    productCards: "tactile-cards",
    quickOrder: "home-cards",
    featured: "layered-card",
    cart: "sticky-strip",
    account: "navigation-link",
    homeSections: Object.freeze(["announcement", "hero", "featured", "categories", "quickOrder"]),
  }),
});

export const layoutChoices = Object.freeze(Object.values(layoutDefinitions));

export const previewSampleCategories = Object.freeze([
  { id: "sample-coffee", name: "Coffee" }, { id: "sample-breakfast", name: "Breakfast" }, { id: "sample-bakery", name: "Bakery" },
]);
export const previewSampleProducts = Object.freeze([
  { id: "sample-cappuccino", name: "Cappuccino", category: "sample-coffee", price: 4.75 },
  { id: "sample-cold-brew", name: "Cold Brew", category: "sample-coffee", price: 4.5 },
  { id: "sample-scone", name: "Blueberry Scone", category: "sample-bakery", price: 4.25 },
  { id: "sample-sandwich", name: "Breakfast Sandwich", category: "sample-breakfast", price: 8.95 },
]);

export function getLayoutDefinition(template) {
  return layoutDefinitions[template] || layoutDefinitions.cozy;
}

export function layoutShowsHomeQuickOrder(template, configuredSections = []) {
  const layout = getLayoutDefinition(template);
  if (layout.quickOrder === "browse-only") return false;
  if (layout.quickOrder === "home-rail") return true;
  return configuredSections.includes("quickOrder");
}

export function layoutShowsHero(template, configuredSections = []) {
  const layout = getLayoutDefinition(template);
  if (layout.hero === "wordmark") return false;
  if (layout.hero === "immersive") return true;
  return configuredSections.includes("hero");
}

export function previewCatalog(categories = [], products = []) {
  const realProducts = products.filter((product) => product.published !== false);
  if (realProducts.length) return { categories, products: realProducts.slice(0, 6), sample: false };
  return { categories: previewSampleCategories, products: previewSampleProducts, sample: true };
}
