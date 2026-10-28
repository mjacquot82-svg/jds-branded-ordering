import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { validateProductImage } from "../../src/design/imageRequirements.js";
import { isProductDraftDirty } from "../../src/admin/productDraft.js";

const source = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("product image validation rejects local rule failures and warns for non-square images", () => {
  assert.match(validateProductImage({ type: "image/jpeg", size: 1000, width: 640, height: 640 }).errors[0], /too small.*800 × 800/i);
  assert.match(validateProductImage({ type: "image/gif", size: 1000, width: 800, height: 800 }).errors[0], /PNG, JPEG, or WebP/);
  assert.match(validateProductImage({ type: "image/webp", size: 10_000_001, width: 800, height: 800 }).errors[0], /larger than 10 MB/);
  assert.deepEqual(validateProductImage({ type: "image/png", size: 1000, width: 800, height: 800 }), { errors: [], warnings: [] });
  assert.match(validateProductImage({ type: "image/png", size: 1000, width: 1200, height: 800 }).warnings[0], /square 1:1.*recommended/i);
});

test("product image control owns busy, error, preview, retry, replace, remove, and library feedback", async () => {
  const page = await source("../../src/admin/ProductsPage.jsx");
  assert.match(page, /setImageFeedback\(\{ status: "busy", message: "Checking image…"/);
  assert.match(page, /setImageFeedback\(\{ status: "error", message: validation\.errors\[0\]/);
  assert.match(page, /Product image uploaded\./);
  assert.match(page, /Selected product image/);
  assert.match(page, /"Replace with my own"/);
  assert.match(page, />Remove image<\/button>/);
  assert.match(page, />Choose from my images</);
  assert.match(page, /Your current product image and draft were not changed\./);
  assert.match(page, /disabled=\{uploading\}/);
  assert.doesNotMatch(page, /catch \(nextError\)[^{]*\{[^}]*updateField\("image", ""\)/);
});

test("canonical modifier manager round-trip keeps every product draft field alive", async () => {
  const [page, manager] = await Promise.all([source("../../src/admin/ProductsPage.jsx"), source("../../src/admin/ModifierManager.jsx")]);
  assert.match(page, /if \(canEdit && managingModifiers\) return <ModifierManager/);
  assert.match(page, /onClose=\{\(\) => setManagingModifiers\(false\)\}/);
  assert.match(page, /onClick=\{\(\) => setManagingModifiers\(true\)\}>Manage modifiers/);
  assert.doesNotMatch(page, /requestProductAction\([^\n]*Manage modifiers/);
  assert.match(manager, /returnLabel = "Menu items"/);
  assert.match(manager, /await onSaveCustomization/);

  const latte = { id: "", name: "Latte", description: "Espresso with steamed milk.", price: "4.75", category: "coffee", image: "media-17", available: true, published: true, featured: false, lunchSpecial: false, modifierGroupIds: [], variants: [{ key: "large", name: "Large", price: "5.50", active: true, sort_order: 0 }] };
  assert.equal(isProductDraftDirty(latte, { ...latte, name: "", description: "", price: "", image: "", variants: [] }), true);
  assert.equal(latte.variants[0].name, "Large");
  assert.equal(latte.variants[0].price, "5.50");
  assert.equal(latte.image, "media-17");
});

test("genuine product abandonment still uses the dirty-draft guard", async () => {
  const page = await source("../../src/admin/ProductsPage.jsx");
  assert.match(page, /requestProductAction\(\(\) => startEdit\(product\)\)/);
  assert.match(page, /requestProductAction\(resetForm\)/);
  assert.match(page, /window\.addEventListener\("beforeunload", beforeUnload\)/);
  assert.match(page, /Unsaved product changes/);
  assert.match(page, /Leave without saving/);
});
