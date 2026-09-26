import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { filterStarterMedia, productImageSourceLabel, starterCategoryLabel } from "../../src/services/starterMedia.js";

const source = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("picker offers only starter images with shipped artwork, with friendly category labels", async () => {
  const page = await source("../../src/admin/ProductsPage.jsx");
  assert.match(page, /starterMedia\.filter\(\(asset\) => asset\.available\)/);
  assert.match(page, /filterStarterMedia\(availableStarterMedia/);
  assert.match(page, /suggestedStarterMedia\(availableStarterMedia/);
  assert.match(page, /starterCategoryLabel\(item\)/);
  assert.doesNotMatch(page, /item\.replaceAll\("-"," "\)/);
  assert.match(page, /Starter images aren’t available right now\. Upload your own photo instead\./);
  assert.match(page, /No starter image matches that search/);
  const assets = [{ key: "latte", name: "Latte", category: "coffee", tags: [], available: true }, { key: "americano", name: "Americano", category: "coffee", tags: [], available: false }];
  assert.deepEqual(filterStarterMedia(assets.filter((asset) => asset.available), {}).map((asset) => asset.key), ["latte"]);
  assert.equal(starterCategoryLabel("sandwiches-wraps"), "Sandwiches & Wraps");
});

test("starter selections are clearly marked as illustrated placeholders and show a live card preview", async () => {
  const page = await source("../../src/admin/ProductsPage.jsx");
  assert.match(page, /Illustrated placeholder — replace it with your own photo anytime\./);
  assert.match(page, /className="product-card-mini-preview"/);
  assert.match(page, /aria-pressed=\{isSelected\}/);
  assert.match(page, /productImageSourceLabel\(formProduct\.image\)/);
  assert.equal(productImageSourceLabel("starter:cafe-restaurant/latte@1"), "Illustrated starter image");
  assert.equal(productImageSourceLabel("/api/v1/storefront/media/0b6e6f7a-3f5b-4c1f-9b32-6c8f3d5a1e20"), "Your photo");
});

test("product list rows show image thumbnails through owner-safe URLs", async () => {
  const page = await source("../../src/admin/ProductsPage.jsx");
  assert.match(page, /className="product-row-thumb"/);
  assert.match(page, /src=\{ownerProductImageUrl\(product\.image\)\}/);
});

test("prospects see the 5 MB demo photo limit and can delete unused uploads through the tenant archive endpoint", async () => {
  const page = await source("../../src/admin/ProductsPage.jsx");
  assert.match(page, /fetchDemoStatus\(\)\.then\(\(status\)=>setDemoLimits\(status\?\.isProspect \? status\.limits \|\| null : null\)\)/);
  assert.match(page, /demoLimits\?\.maxImageBytes && file\.size > demoLimits\.maxImageBytes/);
  assert.match(page, /the free demo limit per photo/);
  assert.match(page, /await archiveMedia\(asset\.id, session\.csrf_token\)/);
  assert.match(page, /Delete unused photo/);
  assert.match(page, /asset\.purpose==="product"/);
  assert.match(page, /const inUse=formProduct\.image===asset\.url\|\|products\.some/);
  assert.match(page, /Starter images don’t count\./);
  assert.doesNotMatch(page, /storageKey/);
});

test("platform admin only offers promote-to-live with platform write access", async () => {
  const page = await source("../../src/admin/PlatformAdminPage.jsx");
  assert.match(page, /hasPlatformCapability\(session,"platform\.organizations\.write"\)/);
  assert.match(page, /\{canPromote\?<button/);
});
