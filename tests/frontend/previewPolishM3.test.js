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

test("deep links to /admin/platform wait for platform capabilities instead of bouncing to Overview", async () => {
  const context = await source("../../src/auth/OwnerAuthContext.jsx");
  assert.match(context, /platform_capabilities: capabilities, platform_capabilities_loaded: true/);
  assert.equal((context.match(/platform_capabilities: \[\], platform_capabilities_loaded: false/g) || []).length, 2);
  const guard = await source("../../src/auth/RequireOwner.jsx");
  const waitIndex = guard.indexOf('session.platform_capabilities_loaded === false && location.pathname.startsWith("/admin/platform")');
  assert.ok(waitIndex > 0);
  assert.ok(waitIndex < guard.indexOf('if (session) return <Navigate replace to={operationsLinks(session)[0]?.to'));
  assert.ok(guard.indexOf("canAccessOwnerPath(session, location.pathname)") < waitIndex, "authorized sessions render before the wait state");
});

test("platform admin shows prospect and activation times in local time, not raw UTC ISO strings", async () => {
  const page = await source("../../src/admin/PlatformAdminPage.jsx");
  assert.match(page, /export function formatPlatformTime\(value\)/);
  assert.match(page, /created \{formatPlatformTime\(item\.createdAt\)\}/);
  assert.doesNotMatch(page, /\{item\.createdAt\}/);
});

test("wizard footer keeps Back at its natural size beside the save-or-cancel hint", async () => {
  const css = await source("../../src/style.css");
  assert.match(css, /\.wizard-actions\{align-items:flex-end\}\.wizard-actions>\.secondary-button\{flex:0 0 auto\}/);
});

test("modern-layout owner preview rows scroll sideways instead of hiding products", async () => {
  const css = await source("../../src/style.css");
  assert.match(css, /\.full-layout-modern \.preview-products\{overflow-x:auto;overflow-y:hidden;/);
  assert.match(css, /@media\(max-width:600px\)\{\.full-layout-modern \.preview-products\{grid-template-columns:none;grid-auto-columns:minmax\(200px,78%\)\}\}/);
  assert.match(css, /\.full-design-preview>main\{grid-template-columns:minmax\(0,1fr\)\}\.full-design-preview \.preview-catalog-section\{min-width:0\}/);
});

test("free demos without a hero photo get an intentional starter hero with a readable activation note", async () => {
  const page = await source("../../src/admin/DesignPreviewPage.jsx");
  assert.match(page, /export function showDemoHero\(\{ isProspect = false, hasHeroImage = false \} = \{\}\) \{\n  return isProspect === true && !hasHeroImage;/);
  assert.match(page, /const demoHero=showDemoHero\(\{isProspect,hasHeroImage:Boolean\(hero\)\}\)/);
  assert.match(page, /<small>Ordering opens after activation<\/small>/);
  assert.match(page, /<h1>\{design\.tagline\|\|/);
  assert.match(page, /DEMO_HERO_STARTERS\.map/);
  for (const key of ["latte", "plain-croissant", "muffin"]) assert.match(page, new RegExp(`starter:cafe-restaurant/${key}@1`));
  // the non-demo hero branch (live stores / own photo) is unchanged
  assert.match(page, /:<section className=\{`full-hero-composition full-hero-\$\{layout\.id\}`\} key="hero"><header className=\{heroContent\.cta&&layout\.id==="modern"\?"has-hero-content":""\} style=\{\{aspectRatio:layout\.heroSlot\.aspectRatio\}\}>/);
  const css = await source("../../src/style.css");
  assert.match(css, /\.full-design-preview \.demo-hero-cta button:disabled\{[^}]*background:#fff;color:#1f2420;[^}]*opacity:1/);
});

test("on phones Edit is the prominent product action and secondary actions share a compact grid", async () => {
  const page = await source("../../src/admin/ProductsPage.jsx");
  assert.match(page, /<button className="product-edit-button" type="button" onClick=\{\(\) => requestProductAction\(\(\) => startEdit\(product\)\)\}>Edit<\/button>/);
  const css = await source("../../src/style.css");
  assert.match(css, /@media\(max-width:760px\)\{\.product-row-actions\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\);gap:\.5rem\}\.product-row-actions button\{min-height:44px;[^}]*\}\.product-row-actions \.product-edit-button\{grid-column:1\/-1;order:-1;/);
});
