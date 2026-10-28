import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../../${path}`, import.meta.url), "utf8");

test("owner and customer product presentations use real media with stable placeholders", async () => {
  const [phone, fullPreview, home, menu, component, styles] = await Promise.all([
    read("src/design/LayoutPhonePreview.jsx"),
    read("src/admin/DesignPreviewPage.jsx"),
    read("src/pages/HomePage.jsx"),
    read("src/pages/MenuPage.jsx"),
    read("src/components/ProductImage.jsx"),
    read("src/style.css"),
  ]);
  assert.match(phone, /<ProductImage className="sample-product-image" src=\{product\.image\}/);
  assert.match(fullPreview, /<ProductImage src=\{product\.image\}/);
  assert.match(home, /<ProductImage className="lunch-special-image"/);
  assert.match(home, /<ProductImage className="quick-product-image"/);
  assert.match(menu, /<ProductImage className="product-thumb"/);
  assert.match(component, /onError=\{\(\) => setFailed\(true\)\}/);
  assert.match(component, /product-image-placeholder/);
  assert.match(component, /No photo available for/);
  assert.match(styles, /Stable product media frames prevent broken-image chrome and layout shifts/);
  assert.match(styles, /aspect-ratio:1/);
});
