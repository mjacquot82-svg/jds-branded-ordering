import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { ownerProductImageUrl, productImageSource, productImageSourceLabel, withOwnerProductImage } from "../../src/services/starterMedia.js";

const upload = "/api/v1/storefront/media/9b85ecfc-0704-428f-a420-6021c1a45ada";

test("owner previews resolve starter references and tenant uploads to displayable URLs", () => {
  assert.equal(ownerProductImageUrl("starter:cafe-restaurant/latte@1"), "/api/v1/storefront/starter-media/cafe-restaurant/latte?version=1");
  assert.equal(ownerProductImageUrl(upload), "/api/v1/owner/media/9b85ecfc-0704-428f-a420-6021c1a45ada/content");
  assert.equal(ownerProductImageUrl(""), "");
  assert.equal(ownerProductImageUrl(null), "");
  assert.equal(ownerProductImageUrl("/legacy/seed.png"), "/legacy/seed.png");
});

test("product image sources are distinguished without exposing storage details", () => {
  assert.equal(productImageSource("starter:cafe-restaurant/latte@1"), "starter");
  assert.equal(productImageSource(upload), "upload");
  assert.equal(productImageSource(""), "none");
  assert.equal(productImageSource("starter:../../etc/passwd@1"), "legacy");
  assert.equal(productImageSource("/api/v1/storefront/media/not-a-uuid"), "legacy");
  assert.equal(productImageSourceLabel(upload), "Your photo");
  assert.equal(productImageSourceLabel("starter:cafe-restaurant/latte@1"), "Illustrated starter image");
  assert.deepEqual(withOwnerProductImage({ name: "Latte", image: "starter:cafe-restaurant/latte@1" }).image, "/api/v1/storefront/starter-media/cafe-restaurant/latte?version=1");
});

test("phone preview and full preview render owner-resolved product images", async () => {
  const phone = await readFile(new URL("../../src/design/LayoutPhonePreview.jsx", import.meta.url), "utf8");
  const full = await readFile(new URL("../../src/admin/DesignPreviewPage.jsx", import.meta.url), "utf8");
  assert.match(phone, /products\.map\(withOwnerProductImage\)/);
  assert.match(full, /catalogProducts\.map\(withOwnerProductImage\)/);
});
