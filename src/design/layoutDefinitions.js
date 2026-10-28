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
    defaultColors: Object.freeze({ primary: "#243b53", accent: "#e07a5f", background: "#f5f7fa", surface: "#ffffff", text: "#1f2933" }),
    slots: Object.freeze({ logo: "optional", hero: "optional", announcement: "optional", quickOrder: "required" }),
    logoSlot: Object.freeze({ aspectRatio: 3, treatment: "compact-header" }),
    heroSlot: Object.freeze({ aspectRatio: 16/9, treatment: "immersive-overlay" }),
    imageSlots: Object.freeze(["logo", "modernHero", "appIcon"]),
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
    defaultColors: Object.freeze({ primary: "#2f3437", accent: "#747b80", background: "#f7f7f5", surface: "#ffffff", text: "#202427" }),
    slots: Object.freeze({ logo: "optional", hero: "unsupported", announcement: "optional", quickOrder: "unsupported" }),
    logoSlot: Object.freeze({ aspectRatio: 3, treatment: "editorial-header" }),
    heroSlot: null,
    imageSlots: Object.freeze(["logo", "appIcon"]),
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
    defaultColors: Object.freeze({ primary: "#6f7d5f", accent: "#b98564", background: "#f7f0e6", surface: "#ffffff", text: "#2f3328" }),
    slots: Object.freeze({ logo: "optional", hero: "optional", announcement: "optional", quickOrder: "optional" }),
    logoSlot: Object.freeze({ aspectRatio: 5/2, treatment: "cafe-header" }),
    heroSlot: Object.freeze({ aspectRatio: 2, treatment: "framed-overlay" }),
    imageSlots: Object.freeze(["logo", "cozyHero", "appIcon"]),
    homeSections: Object.freeze(["announcement", "hero", "featured", "categories", "quickOrder"]),
  }),
});

export const layoutChoices = Object.freeze(Object.values(layoutDefinitions));

const capabilityLanguage = Object.freeze({
  hero: Object.freeze({ immersive: "Large visual hero", wordmark: "No large hero — menu-first introduction", "framed-photo": "Warm, café-style hero" }),
  navigation: Object.freeze({ "mobile-dock": "Bottom mobile navigation", editorial: "Compact editorial navigation", "cafe-tabs": "Café-style mobile tabs" }),
  categories: Object.freeze({ "visual-grid": "Image-forward category grid", "compact-tabs": "Compact category tabs", "tile-grid": "Friendly category tiles" }),
  productCards: Object.freeze({ "media-cards": "Image-forward product cards", "editorial-rows": "Compact menu rows", "tactile-cards": "Warm café product cards" }),
  quickOrder: Object.freeze({ "home-rail": "Quick Order is always on Home", "browse-only": "No Quick Order on Home", "home-cards": "Quick Order can be shown on Home" }),
  featured: Object.freeze({ "hero-followup": "Featured menu content follows the hero", inline: "Menu highlights stay compact", "layered-card": "Featured favourites get their own card" }),
  cart: Object.freeze({ "floating-status": "Prominent bag status and ordering action", "header-link": "Simple cart link in the header", "sticky-strip": "Visible bag strip with café styling" }),
});

const orderingActionLanguage = Object.freeze({ immersive: "Prominent Start an order action", wordmark: "Subtle Browse menu action", "framed-photo": "Prominent Explore the menu action" });
const densityLanguage = Object.freeze({ modern: "Bold, visual, and fast", minimal: "Clean, focused, and information-dense", cozy: "Warm, familiar, and layered" });

export function describeLayoutCapabilities(layoutOrId) {
  const layout = typeof layoutOrId === "string" ? getLayoutDefinition(layoutOrId) : layoutOrId;
  return Object.freeze({
    hero: capabilityLanguage.hero[layout.hero],
    quickOrder: capabilityLanguage.quickOrder[layout.quickOrder],
    featured: capabilityLanguage.featured[layout.featured],
    categories: capabilityLanguage.categories[layout.categories],
    products: capabilityLanguage.productCards[layout.productCards],
    orderingAction: orderingActionLanguage[layout.hero],
    cart: capabilityLanguage.cart[layout.cart],
    mobileNavigation: capabilityLanguage.navigation[layout.navigation],
    density: densityLanguage[layout.id],
  });
}

export const layoutComparisonRows = Object.freeze([
  ["Hero", "hero"], ["Quick Order on Home", "quickOrder"], ["Featured content", "featured"],
  ["Categories", "categories"], ["Products", "products"], ["Ordering action", "orderingAction"],
  ["Cart", "cart"], ["Mobile navigation", "mobileNavigation"], ["Overall feel", "density"],
].map(([label,key])=>Object.freeze({label,key,values:Object.freeze(Object.fromEntries(layoutChoices.map((layout)=>[layout.id,describeLayoutCapabilities(layout)[key]])))})));

export const previewSampleAnnouncement = "Weekend special available now";

export function previewAnnouncementText(config) {
  if (!config?.announcement?.enabled) return "";
  return config.announcement.text?.trim() || previewSampleAnnouncement;
}

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

export function layoutShowsHero(template, configuredSections = [], branding = {}) {
  const layout = getLayoutDefinition(template);
  if (layout.slots.hero === "unsupported") return false;
  return branding.showHero !== false;
}

export function layoutShowsHeaderLogo(template, branding = {}) {
  return getLayoutDefinition(template).slots.logo !== "unsupported" && branding.showLogo !== false;
}

export function previewCatalog(categories = [], products = []) {
  const realProducts = products.filter((product) => product.published !== false);
  if (realProducts.length) return { categories, products: realProducts.slice(0, 6), sample: false };
  return { categories: previewSampleCategories, products: previewSampleProducts, sample: true };
}
