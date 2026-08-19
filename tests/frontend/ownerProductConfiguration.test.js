import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("create and edit product center the Owner workflow on variants then modifiers", async () => {
  const products = await source("../../src/admin/ProductsPage.jsx");
  assert.match(products, /"Create product"/);
  assert.match(products, />Basic information</);
  assert.match(products, />Variants</);
  assert.match(products, /Which version of this product is being purchased\?/);
  assert.match(products, />Modifiers</);
  assert.match(products, /What can the customer add or change\?/);
  const variantsPosition = products.indexOf(">Variants<");
  assert.ok(variantsPosition < products.indexOf(">Modifiers<", variantsPosition));
});

test("variant rows expose labels, dollar prices, availability, and safe new-row removal", async () => {
  const products = await source("../../src/admin/ProductsPage.jsx");
  assert.match(products, /variant\.price_cents \/ 100/);
  assert.match(products, /placeholder="For example, 16oz Iced"/);
  assert.match(products, />Price</);
  assert.match(products, />Available</);
  assert.match(products, /Add variant<\/button>/);
  assert.match(products, /variant\.id \? <label className="variant-available-toggle"/);
  assert.match(products, /removeNewVariant/);
  assert.doesNotMatch(products, /assignment IDs|group IDs|option IDs|min\/max selections/);
});

test("products without variants clearly use their base price", async () => {
  const products = await source("../../src/admin/ProductsPage.jsx");
  assert.match(products, /No variants added\./);
  assert.match(products, /Customers will order this product at its base price\./);
  assert.match(products, /Used when this product has no available variants\./);
});

test("one product save includes current variants and whole modifier categories", async () => {
  const [products, store] = await Promise.all([
    source("../../src/admin/ProductsPage.jsx"),
    source("../../src/stores/catalogStore.js"),
  ]);
  assert.match(products, /if \(saving\) return/);
  assert.match(products, /const payload = \{[\s\S]*variants \}/);
  assert.match(products, /modifierGroupIds/);
  assert.match(products, /Saving…/);
  assert.match(store, /variants: \(product\.variants \|\| \[\]\)\.map/);
  assert.match(store, /modifier_group_ids:/);
});

test("modifier assignment is category-level with previews and an empty state", async () => {
  const products = await source("../../src/admin/ProductsPage.jsx");
  assert.match(products, /Choose which modifier categories are available on this product\./);
  assert.match(products, /group\.options\.filter\(\(item\) => item\.active\)/);
  assert.match(products, /Available on this product/);
  assert.match(products, /Not available on this product/);
  assert.match(products, /No modifiers have been created yet\./);
  assert.match(products, />Manage modifiers</);
  assert.doesNotMatch(products, /modifierOptionIds/);
});

test("product configuration remains readable across desktop and mobile", async () => {
  const css = await source("../../src/style.css");
  assert.match(css, /main:has\(> \.admin-products-page\), main:has\(> \.modifier-manager\) \{ width: min\(calc\(100% - 48px\), 1360px\); \}/);
  assert.match(css, /\.admin-products-page \.admin-products-layout \{ grid-template-columns: minmax\(480px, \.82fr\) minmax\(620px, 1\.18fr\); gap: 16px; \}/);
  assert.match(css, /\.product-row \{[\s\S]*?grid-template-columns: minmax\(190px, 1fr\) minmax\(170px, auto\);/);
  assert.match(css, /\.product-row-actions \{[\s\S]*?grid-column: 1 \/ -1;[\s\S]*?grid-template-columns: repeat\(3, minmax\(0, 1fr\)\);/);
  assert.match(css, /\.product-quick-tools \{[^}]*grid-template-columns: minmax\(320px, 1fr\) minmax\(180px, \.32fr\) minmax\(190px, \.34fr\);/);
  assert.match(css, /\.modifier-manager \{[^}]*max-width: none;[^}]*width: 100%;/);
  assert.match(css, /\.product-variant-row \{[\s\S]*?grid-template-columns:/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*?\.product-variant-row \{ grid-template-columns:/);
  assert.match(css, /@media \(min-width: 761px\) and \(max-width: 1199px\)[\s\S]*?\.admin-products-page \.admin-products-layout \{ grid-template-columns: 1fr; \}/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*?\.admin-products-layout,[\s\S]*?\.product-row \{[\s\S]*?grid-template-columns: 1fr;/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*?\.product-row-actions \{[\s\S]*?grid-template-columns: 1fr;[\s\S]*?width: 100%;/);
});
