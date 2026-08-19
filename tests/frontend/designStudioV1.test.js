import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const studio = readFileSync(new URL("../../src/admin/DesignStudioPage.jsx", import.meta.url), "utf8");
const preview = readFileSync(new URL("../../src/admin/DesignPreviewPage.jsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../../src/style.css", import.meta.url), "utf8");

test("Design Studio keeps three composition templates and a persistent phone preview", () => {
  for (const template of ["modern", "minimal", "cozy"]) {
    assert.match(studio, new RegExp(`id: "${template}"`));
    assert.match(styles, new RegExp(`\\.template-${template}`));
  }
  assert.match(studio, /phone-preview-wrap/);
  assert.match(styles, /position:sticky/);
});

test("Design Studio supports section visibility, ordering, PWA appearance, and contrast guidance", () => {
  assert.match(studio, /allSections = \["hero", "announcement", "categories", "quickOrder"\]/);
  assert.match(studio, /toggleSection/);
  assert.match(studio, /moveSection/);
  assert.match(studio, /backgroundColor/);
  assert.match(studio, /4\.5:1 contrast/);
});

test("private full preview follows draft section order and never offers checkout", () => {
  assert.match(preview, /design\.sections\.map\(renderSection\)/);
  assert.match(preview, /Checkout and payment are disabled/);
  assert.match(preview, /Preview only/);
  assert.doesNotMatch(preview, /createCloverCheckout|createPendingOrder|Add to cart/);
});
