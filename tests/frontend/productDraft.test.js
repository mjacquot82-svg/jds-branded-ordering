import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { isProductDraftDirty } from "../../src/admin/productDraft.js";

const saved = {
  id: "drip-coffee", name: "Drip Coffee", description: "Freshly brewed", price: "2.05",
  category: "coffee", image: "coffee", available: true, published: true,
  featured: false, lunchSpecial: false, modifierGroupIds: ["milk"],
  variants: [{ id: 10, key: "12oz", name: "12oz", price: "2.05", price_cents: 205, active: true, sort_order: 0 }],
};
const changed = (updates) => ({ ...saved, ...updates });

test("loaded Product is clean and text and price changes become dirty then clean on semantic restore", () => {
  assert.equal(isProductDraftDirty(saved, { ...saved }), false);
  assert.equal(isProductDraftDirty(changed({ description: "Changed" }), saved), true);
  assert.equal(isProductDraftDirty(changed({ description: "Freshly brewed" }), saved), false);
  assert.equal(isProductDraftDirty(changed({ price: "2.50" }), saved), true);
  assert.equal(isProductDraftDirty(changed({ price: "2.050" }), saved), false);
  assert.equal(isProductDraftDirty(changed({ name: " Drip Coffee ", description: "Freshly brewed " }), saved), false);
});

test("Product variants compare the values and ordering persisted by Save product", () => {
  const edited = changed({ variants: [{ ...saved.variants[0], name: "Small" }] });
  assert.equal(isProductDraftDirty(edited, saved), true);
  assert.equal(isProductDraftDirty(changed({ variants: [{ ...edited.variants[0], name: "12oz" }] }), saved), false);
  const added = changed({ variants: [...saved.variants, { key: "new-key", name: "Large", price: "3.00", active: true }] });
  assert.equal(isProductDraftDirty(added, saved), true);
  assert.equal(isProductDraftDirty(changed({ variants: added.variants.slice(0, -1) }), saved), false);
});

test("Product modifier assignments are semantic sets and revert cleanly", () => {
  assert.equal(isProductDraftDirty(changed({ modifierGroupIds: ["milk", "syrup"] }), saved), true);
  assert.equal(isProductDraftDirty(changed({ modifierGroupIds: ["milk"] }), saved), false);
  assert.equal(isProductDraftDirty(changed({ modifierGroupIds: ["milk", "milk"] }), saved), false);
});

test("Product Save-owned image and placement fields are covered", () => {
  for (const update of [{ image: "tea" }, { category: "tea" }, { available: false }, { published: false }, { featured: true }, { lunchSpecial: true }]) {
    assert.equal(isProductDraftDirty(changed(update), saved), true);
  }
});

test("untouched Create Product is clean but meaningful input is dirty", () => {
  const blank = { name: "", description: "", price: "", category: "", image: "", available: true, published: true, featured: false, lunchSpecial: false, variants: [], modifierGroupIds: [] };
  assert.equal(isProductDraftDirty(blank, { ...blank }, "coffee"), false);
  assert.equal(isProductDraftDirty({ ...blank, name: "Latte" }, blank, "coffee"), true);
});

test("Product page follows Loyalty navigation guards and Save baseline lifecycle", async () => {
  const page = await readFile(new URL("../../src/admin/ProductsPage.jsx", import.meta.url), "utf8");
  assert.match(page, /setSavedProduct\(next\)/);
  assert.match(page, /if \(savingRef\.current\) return/);
  assert.match(page, /catch \(nextError\) \{ setNotice\(nextError\.message\); \}/);
  assert.doesNotMatch(page, /catch \(nextError\)[^}]*setSavedProduct/);
  assert.match(page, /window\.addEventListener\("beforeunload", beforeUnload\)/);
  assert.match(page, /window\.removeEventListener\("beforeunload", beforeUnload\)/);
  assert.match(page, /window\.navigation/);
  assert.match(page, /navigationApi\.traverseTo\(key\)/);
  assert.match(page, /document\.addEventListener\("click", onClick, true\)/);
  assert.match(page, /requestProductAction\(\(\) => startEdit\(product\)\)/);
  assert.match(page, /requestProductAction\(\(\) => \{ resetForm\(\); setManagingModifiers\(true\); \}\)/);
  assert.match(page, /<dialog aria-describedby="unsaved-product-message" aria-labelledby="unsaved-product-title"/);
  assert.match(page, />Stay<\/button>/);
  assert.match(page, />Leave without saving<\/button>/);
});

test("immediate Product row and Modifier Library API saves are excluded from Product draft updates", async () => {
  const [page, manager] = await Promise.all([
    readFile(new URL("../../src/admin/ProductsPage.jsx", import.meta.url), "utf8"),
    readFile(new URL("../../src/admin/ModifierManager.jsx", import.meta.url), "utf8"),
  ]);
  assert.match(page, /await setProductAvailability\(product\.id, next\)/);
  assert.match(page, /await setLunchSpecial\(product\.lunchSpecial \? null : product\.id\)/);
  assert.doesNotMatch(page, /toggleAvailability[\s\S]*?setFormProduct/);
  assert.match(manager, /await onSaveCustomization/);
  assert.doesNotMatch(manager, /setSavedProduct|isProductDraftDirty/);
});
