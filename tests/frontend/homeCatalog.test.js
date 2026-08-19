import assert from "node:assert/strict";
import test from "node:test";

import {
  createQuickOrderItems,
  createHomeCatalogView,
  getHomeCategoryById,
} from "../../src/services/homeCatalog.js";

function adaptedCatalog() {
  return {
    categories: [
      { id: "coffee", name: "Coffee" },
      { id: "espresso", name: "Espresso" },
      { id: "pastries", name: "Pastries" },
      { id: "iced-drinks", name: "Iced Drinks" },
    ],
    products: [
      {
        id: "drip-coffee",
        category: "coffee",
        name: "Drip Coffee",
        available: true,
        featured: true,
        lunchSpecial: false,
        sortOrder: 0,
      },
      {
        id: "cold-brew",
        category: "iced-drinks",
        name: "Cold Brew",
        available: true,
        featured: true,
        lunchSpecial: true,
        sortOrder: 1,
      },
      {
        id: "latte",
        category: "espresso",
        name: "Latte",
        available: true,
        featured: true,
        lunchSpecial: false,
        sortOrder: 2,
      },
      {
        id: "croissant",
        category: "pastries",
        name: "Butter Croissant",
        available: true,
        featured: true,
        lunchSpecial: false,
        sortOrder: 7,
      },
      {
        id: "muffin",
        category: "pastries",
        name: "Blueberry Muffin",
        available: true,
        featured: false,
        lunchSpecial: false,
        sortOrder: 8,
      },
      {
        id: "hidden-tea",
        category: "tea",
        name: "Hidden Tea",
        available: false,
        featured: true,
        lunchSpecial: false,
        sortOrder: 9,
      },
    ],
  };
}

test("Home preserves featured product order and crafted-drink count", () => {
  const catalog = adaptedCatalog();
  const view = createHomeCatalogView("ready", catalog);

  assert.equal(view.status, "ready");
  assert.equal(view.categories, catalog.categories);
  assert.deepEqual(
    view.popularItems.map((product) => product.id),
    ["drip-coffee", "cold-brew", "latte", "croissant"]
  );
  assert.equal(view.coffeeCount, 3);
  assert.equal(view.lunchSpecial.id, "cold-brew");
});

test("Home resolves category summaries from adapted API categories", () => {
  const categories = adaptedCatalog().categories;

  assert.equal(getHomeCategoryById(categories, "espresso").name, "Espresso");
  assert.equal(getHomeCategoryById(categories, "missing"), undefined);
});

test("Home produces safe loading and error projections without stale data", () => {
  const loading = createHomeCatalogView("loading", null);
  const error = createHomeCatalogView("error", null);

  assert.deepEqual(loading, {
    status: "loading",
    categories: [],
    popularItems: [],
    lunchSpecial: null,
    coffeeCount: 0,
  });
  assert.deepEqual(error, {
    status: "error",
    categories: [],
    popularItems: [],
    lunchSpecial: null,
    coffeeCount: 0,
  });
});

test("Home handles a successful empty catalog", () => {
  assert.deepEqual(
    createHomeCatalogView("empty", {
      categories: [],
      products: [],
    }),
    {
      status: "empty",
      categories: [],
      popularItems: [],
      lunchSpecial: null,
      coffeeCount: 0,
    }
  );
});

test("Home falls back cleanly when no lunch special is configured", () => {
  const catalog = adaptedCatalog();
  catalog.products.forEach((product) => { product.lunchSpecial = false; });

  assert.equal(createHomeCatalogView("ready", catalog).lunchSpecial, null);
});

test("Quick Order prioritizes four featured products and still fills six unique slots", () => {
  const products = Array.from({ length: 8 }, (_, index) => ({
    id: `product-${index + 1}`,
    available: true,
    featured: index < 6,
  }));

  const quickOrder = createQuickOrderItems(products);

  assert.equal(quickOrder.length, 6);
  assert.deepEqual(quickOrder.slice(0, 4).map((product) => product.id), [
    "product-1", "product-2", "product-3", "product-4",
  ]);
  assert.equal(new Set(quickOrder.map((product) => product.id)).size, 6);
});

test("Quick Order excludes unavailable products while filling from other available products", () => {
  const products = Array.from({ length: 8 }, (_, index) => ({
    id: `product-${index + 1}`,
    available: index !== 1,
    featured: index < 5,
  }));

  const quickOrder = createQuickOrderItems(products);

  assert.equal(quickOrder.length, 6);
  assert.ok(quickOrder.every((product) => product.available));
  assert.ok(!quickOrder.some((product) => product.id === "product-2"));
  assert.equal(new Set(quickOrder.map((product) => product.id)).size, 6);
});

test("Quick Order puts ranked history first and fills without duplicates", () => {
  const products = Array.from({ length: 8 }, (_, index) => ({
    id: `product-${index + 1}`,
    backendId: String(index + 1),
    available: true,
    featured: index < 4,
  }));
  const quickOrder = createQuickOrderItems(products, {
    personalizedProductIds: ["6", "2", "6"],
  });

  assert.deepEqual(quickOrder.map((product) => product.id), [
    "product-6", "product-2", "product-1", "product-3", "product-4", "product-5",
  ]);
  assert.equal(new Set(quickOrder.map((product) => product.id)).size, 6);
});

test("Quick Order ignores history absent from the current available catalog", () => {
  const products = Array.from({ length: 7 }, (_, index) => ({
    id: `product-${index + 1}`,
    backendId: String(index + 1),
    available: index !== 5,
    featured: index < 4,
  }));
  const quickOrder = createQuickOrderItems(products, {
    personalizedProductIds: ["6", "999", "5"],
  });

  assert.equal(quickOrder[0].id, "product-5");
  assert.ok(!quickOrder.some((product) => product.id === "product-6"));
  assert.equal(quickOrder.length, 6);
});
