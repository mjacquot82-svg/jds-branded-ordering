import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("owner preview loads product images eagerly so full-page previews never show blank rows", async () => {
  const image = await source("../../src/components/ProductImage.jsx");
  assert.match(image, /loading = "lazy"/);
  assert.match(image, /loading=\{loading\}/);
  const preview = await source("../../src/admin/DesignPreviewPage.jsx");
  assert.match(preview, /<ProductImage[^>]*loading="eager"/);
});

test("owner previews show whole product images at 4:3, scoped away from customer storefront classes", async () => {
  const css = await source("../../src/style.css");
  assert.match(css, /\.full-design-preview \.preview-products article>img,\.full-design-preview \.preview-products article>\.product-image-placeholder\{height:auto;aspect-ratio:4\/3/);
  assert.match(css, /\.layout-product-grid \.sample-product-image\{height:auto;aspect-ratio:4\/3/);
  const m3Block = css.slice(css.indexOf("/* M3 owner previews only"));
  assert.doesNotMatch(m3Block, /\.product-thumb|\.quick-product-image|\.storefront-/);
});

test("choosing an image tells the owner to save, with a primary save button beside the image controls", async () => {
  const page = await source("../../src/admin/ProductsPage.jsx");
  assert.match(page, /formProduct\.image!==savedProduct\.image\?<div className="product-image-save-hint" role="status">/);
  assert.match(page, /Image chosen — not saved yet\.<\/strong> Save to show it on your menu and in your preview\./);
  assert.match(page, /product-image-save-hint"[^]*?<button className="primary-button" disabled=\{saving\} type="submit">/);
});

test("category manager controls are styled, finger-sized and use the wizard font", async () => {
  const css = await source("../../src/style.css");
  assert.match(css, /\.catalog-category-manager \.section-heading h2\{[^}]*font-family:inherit/);
  assert.match(css, /\.category-management-list article button\{min-height:44px;[^}]*font:inherit/);
  assert.match(css, /\.category-management-list article \.category-delete-button:not\(:disabled\)/);
  const page = await source("../../src/admin/ProductsPage.jsx");
  assert.match(page, /className="category-delete-button"/);
});

test("opening another product resets the starter search so suggestions for the new product show", async () => {
  const page = await source("../../src/admin/ProductsPage.jsx");
  for (const fn of ["startCreate", "startEdit"]) {
    const line = page.split("\n").find((item) => item.includes(`const ${fn} = useCallback`));
    assert.match(line, /setStarterQuery\(""\); setStarterCategory\("all"\); setStarterPickerOpen\(false\); setImageLibraryOpen\(false\);/);
  }
});
