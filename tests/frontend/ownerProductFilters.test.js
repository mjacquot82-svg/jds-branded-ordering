import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { visibleProducts } from "../../src/services/ownerProductFilters.js";

const products = [
  { id: "tea", name: "Tea", description: "Herbal", category: "drinks", available: true, published: true },
  { id: "americano", name: "Americano", description: "Espresso and water", category: "drinks", available: false, published: true },
  { id: "muffin", name: "Muffin", description: "Blueberry", category: "food", available: true, published: false },
];

test("product tools search and sort alphabetically", () => {
  assert.deepEqual(visibleProducts(products).map(({ id }) => id), ["americano", "muffin", "tea"]);
  assert.deepEqual(visibleProducts(products, { query: "espresso" }).map(({ id }) => id), ["americano"]);
});

test("product tools distinguish unavailable from hidden and preserve category scope", () => {
  assert.deepEqual(visibleProducts(products, { status: "unavailable" }).map(({ id }) => id), ["americano"]);
  assert.deepEqual(visibleProducts(products, { status: "hidden" }).map(({ id }) => id), ["muffin"]);
  assert.deepEqual(visibleProducts(products, { category: "drinks", status: "available" }).map(({ id }) => id), ["tea"]);
});

test("Product configuration exposes clear controls for existing catalog states", async () => {
  const page = await readFile(new URL("../../src/admin/ProductsPage.jsx", import.meta.url), "utf8");
  assert.match(page, /Available for online ordering/);
  assert.match(page, /Visible on customer menu/);
  assert.match(page, /Turn off to hide this product without archiving it/);
  assert.match(page, /<strong>Featured<\/strong>/);
  assert.match(page, /<strong>Lunch special<\/strong>/);
  assert.match(page, /id="product-modifiers-heading">Modifiers<\/h3>/);
  assert.match(page, /Choose which modifier categories are available on this product/);
  assert.match(page, /Hidden from menu/);
  assert.doesNotMatch(page, /Available on today’s menu|Unavailable today|Featured placement and options/);
});
