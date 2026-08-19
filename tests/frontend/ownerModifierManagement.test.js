import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { dollarsToCents, toOwnerCustomizationWrite } from "../../src/services/modifierMoney.js";

const source = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("owner modifier dollar input converts exactly to integer cents", () => {
  assert.equal(dollarsToCents("0"), 0);
  assert.equal(dollarsToCents("0.75"), 75);
  assert.equal(dollarsToCents("12.3"), 1230);
  assert.equal(dollarsToCents("-0.25"), null);
  assert.equal(dollarsToCents("0.001"), null);
  assert.equal(dollarsToCents("not money"), null);
});

test("Products exposes Menu items and Modifiers as one catalog experience", async () => {
  const [products, manager] = await Promise.all([
    source("../../src/admin/ProductsPage.jsx"),
    source("../../src/admin/ModifierManager.jsx"),
  ]);
  assert.match(products, /aria-label="Products sections"/);
  assert.match(products, />Menu items</);
  assert.match(products, />Modifiers</);
  assert.match(manager, /Product catalog/);
  assert.match(manager, />Menu items</);
  assert.doesNotMatch(manager, /Customer options/);
  assert.doesNotMatch(manager, /Modifier group/);
});

test("zero-modifier first use is a simple empty state", async () => {
  const manager = await source("../../src/admin/ModifierManager.jsx");
  assert.match(manager, /No modifiers yet\./);
  assert.match(manager, /Create modifier categories for things customers can add or choose/);
  assert.match(manager, />Add modifier category</);
  assert.doesNotMatch(manager, /Create example/);
});

test("simple category creation uses safe optional choose-one defaults", async () => {
  const manager = await source("../../src/admin/ModifierManager.jsx");
  assert.match(manager, /selectionType: "single", required: false/);
  assert.match(manager, /minSelections: 0, maxSelections: 1, active: true/);
  assert.match(manager, /choices: \[\]/);
  assert.match(manager, /New modifier category/);
  assert.match(manager, /Save modifier category/);

  const base = { name: "Milk", description: "", selectionType: "single", required: false, active: true, choices: [], sortOrder: 0 };
  assert.deepEqual(toOwnerCustomizationWrite(base, 4).group, {
    name: "Milk", description: "", selection_type: "single", required: false, allow_quantity: false,
    min_selections: 0, max_selections: 1, active: true, sort_order: 0,
  });
});

test("advanced category settings are collapsed and reveal conditional limits", async () => {
  const manager = await source("../../src/admin/ModifierManager.jsx");
  assert.match(manager, /<details className="modifier-advanced"><summary>Advanced settings<\/summary>/);
  assert.doesNotMatch(manager, /<details className="modifier-advanced" open/);
  assert.match(manager, /One option/);
  assert.match(manager, /Multiple options/);
  assert.match(manager, /Allow quantities/);
  assert.match(manager, /Does the customer need to make a choice/);
  assert.match(manager, /No — they can choose None/);
  assert.match(manager, /Yes — they must choose something/);
  assert.match(manager, /Selection limits/);
  assert.match(manager, /Maximum total selections/);
  assert.doesNotMatch(manager, />Display order</);
});

test("modifier catalog supports add, edit, prices, and safe disable", async () => {
  const manager = await source("../../src/admin/ModifierManager.jsx");
  assert.match(manager, /modifier-category-list/);
  assert.match(manager, /\+ Add modifier/);
  assert.match(manager, /Extra price/);
  assert.match(manager, /placeholder="0\.00"/);
  assert.match(manager, /Make unavailable/);
  assert.match(manager, /Make available/);
  assert.match(manager, /retained for order history/);
  assert.match(manager, /priceLabel\(modifier\.priceAdjustmentCents\)/);
  assert.doesNotMatch(manager, /price_adjustment_cents/);
});

test("product editor accurately assigns whole categories and previews their modifiers", async () => {
  const products = await source("../../src/admin/ProductsPage.jsx");
  assert.match(products, /Choose which modifier categories are available on this product/);
  assert.match(products, /modifierGroupIds\.includes\(group\.id\)/);
  assert.match(products, /group\.options\.filter\(\(item\) => item\.active\)/);
  assert.match(products, /Available on this product/);
  assert.match(products, /No modifiers have been created yet\./);
  assert.match(products, />Manage modifiers</);
  assert.doesNotMatch(products, /modifierOptionIds/);
});

test("responsive styles keep catalog controls and modifier rows touch-friendly", async () => {
  const css = await source("../../src/style.css");
  assert.match(css, /\.modifier-category-list \{ display: grid/);
  assert.match(css, /\.modifier-edit-row \{[\s\S]*?grid-template-columns:/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*?\.products-view-switch button \{ flex: 1; \}/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*?\.modifier-edit-row, \.modifier-limits \{ grid-template-columns: 1fr; \}/);
  assert.match(css, /\.product-modifier-options label \{[\s\S]*?min-height: 68px/);
});
