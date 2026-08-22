import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const css = fs.readFileSync(new URL("../../src/style.css", import.meta.url), "utf8");
const preview = fs.readFileSync(new URL("../../src/design/LayoutPhonePreview.jsx", import.meta.url), "utf8");
const studio = fs.readFileSync(new URL("../../src/admin/DesignStudioPage.jsx", import.meta.url), "utf8");

test("phone root is a fixed, vertically scrolling mobile viewport", () => {
  assert.match(css, /\.phone-preview\{width:390px;max-width:100%;min-width:0;overflow-x:hidden;overflow-y:auto/);
  assert.doesNotMatch(css, /\.phone-preview\{[^}]*overflow-x:auto/);
  assert.match(css, /\.embedded-wizard-design \.phone-preview\{width:430px;max-width:100%\}/);
});

test("Modern, Minimal, and Cozy internals remain bounded", () => {
  for (const layout of ["modern", "minimal", "cozy"]) {
    assert.match(preview, new RegExp(`layout\\.id===\"${layout}\"|layout-${layout}|${layout}-`));
  }
  assert.match(css, /grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/);
  assert.match(css, /grid-template-columns:minmax\(0,1fr\) auto auto/);
  assert.match(css, /\.layout-preview-content>\*,\.layout-category-section,\.layout-quick-order,\.minimal-menu-preview,\.cozy-feature\{min-width:0;max-width:100%\}/);
});

test("only the explicit Quick Order rail owns horizontal interaction", () => {
  assert.match(preview, /className="layout-quick-order-rail"/);
  assert.match(css, /\.layout-quick-order-rail\{[^}]*overflow-x:auto;overflow-y:hidden/);
  assert.match(css, /\.layout-quick-order-rail \.layout-product-grid\{[^}]*grid-auto-columns:155px/);
});

test("long preview labels wrap or shrink instead of widening the phone", () => {
  assert.match(css, /overflow-wrap:anywhere/);
  assert.match(css, /\.preview-business-name\{flex:1 1 auto;overflow:hidden/);
  assert.match(css, /\.categories-compact-tabs\{display:flex;flex-wrap:wrap;min-width:0\}/);
  assert.match(preview, /identitySlot=mode==="logo"\?"logo":"tagline"/);
});

test("visual wizard uses a wide desktop canvas and preserves mobile Edit Preview mode", () => {
  assert.match(css, /\.wizard-content:has\(\.embedded-wizard-design\)\{max-width:1840px\}/);
  assert.match(css, /\.embedded-wizard-design\{width:100%;max-width:1740px\}/);
  assert.match(css, /grid-template-columns:minmax\(0,1\.35fr\) minmax\(430px,1fr\)/);
  assert.match(css, /\.embedded-wizard-design \.studio-workspace\{[^}]*align-items:stretch/);
  assert.match(css, /@media\(max-width:960px\)\{\.embedded-wizard-design \.studio-workspace\{grid-template-columns:1fr\}/);
  assert.match(css, /\.studio-workspace\.mobile-edit \.phone-preview-column\{display:none\}/);
  assert.match(css, /\.studio-workspace\.mobile-preview \.studio-controls\{display:none\}/);

  for (const viewport of [1024, 1366, 1440, 1920]) {
    const outerPadding = viewport >= 1366 ? 80 : 48;
    const workspace = Math.min(viewport - outerPadding, 1740);
    const gap = Math.min(44, Math.max(16, viewport * 0.025));
    assert.ok(workspace - 430 - gap > 500, `${viewport}px keeps a comfortable editor beside the complete phone`);
  }
});

test("Step 2 uses a stretched grid column with a separate bounded sticky child",()=>{
  assert.match(studio,/className="phone-preview-column visual-designer-preview-column">\s*<div className="phone-preview-wrap phone-preview-sticky visual-designer-preview-sticky"/);
  assert.match(css,/\.phone-preview-column\{align-self:stretch;min-height:100%\}/);
  assert.match(css,/\.embedded-wizard-design \.phone-preview-sticky\{position:sticky;top:clamp\(\.75rem,2vh,1\.25rem\);width:100%;height:max-content;max-height:none;align-self:start\}/);
  assert.match(css,/\.wizard-design-brand \.phone-preview\{height:clamp\(460px,calc\(100dvh - 10\.5rem\),720px\)\}/);
  assert.match(css,/@media\(max-width:960px\)\{\.embedded-wizard-design \.studio-workspace\{grid-template-columns:1fr\}\.phone-preview-column\{min-height:0\}\.embedded-wizard-design \.phone-preview-sticky\{position:static/);
  assert.match(css,/\.phone-preview\{width:390px;max-width:100%;min-width:0;overflow-x:hidden;overflow-y:auto/);
});
