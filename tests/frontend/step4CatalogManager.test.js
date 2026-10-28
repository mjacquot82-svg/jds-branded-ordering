import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const products = readFileSync(new URL("../../src/admin/ProductsPage.jsx", import.meta.url), "utf8");
const wizard = readFileSync(new URL("../../src/setup/SetupWizard.jsx", import.meta.url), "utf8");
const store = readFileSync(new URL("../../src/stores/catalogStore.js", import.meta.url), "utf8");

test("shared catalog manager is category-first and has one meaningful create entry", () => {
  assert.match(products, /Create your first category/);
  assert.match(products, /Create category/);
  assert.match(products, /startCreate\(categories\[0\]\.id\)/);
  assert.doesNotMatch(products, /Add my first product/);
  assert.match(products, /nameRef\.current\?\.focus/);
});

test("setup and post-launch retain the same manager with shell-specific copy", () => {
  assert.match(wizard, /<ProductsPage setupMode/);
  assert.match(products, /setupMode\?"Build your menu":"Products"/);
  assert.match(store, /addCategory, updateCategory, removeCategory, reorderCategories/);
});

test("authoritative catalog readiness gates Continue", () => {
  assert.match(wizard, /fetchReadiness\(\)/);
  assert.match(wizard, /step==="catalog"&&!readiness\?\.checks\?\.catalog/);
  assert.match(wizard, /Create a visible category and add at least one available product/);
});

test("product media keeps starter, upload, and tenant-owned sources distinct", () => {
  assert.match(products, /Choose a starter image/);
  assert.match(products, /Upload my own/);
  assert.match(products, /Choose from my images/);
  assert.match(products, /uploadMedia\(file,[\s\S]*"product"\)/);
  assert.doesNotMatch(products, /Image URL or token/);
});
