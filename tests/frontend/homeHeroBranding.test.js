import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(new URL("../../src/pages/HomePage.jsx", import.meta.url), "utf8");
const styles = await readFile(new URL("../../src/style.css", import.meta.url), "utf8");

test("Home hero uses the single approved Ladel's asset and removes legacy content", async () => {
  await access(new URL("../../public/cafe.png", import.meta.url));
  assert.equal((home.match(/className="ladels-hero-logo"/g) || []).length, 1);
  assert.match(home, /src="\/cafe\.png" alt="Ladel's Wellness Café"/);
  assert.doesNotMatch(home, /src="\/ladels3\.png"/);
  assert.doesNotMatch(home, /src="\/ladels\.png"/);
  assert.doesNotMatch(home, /Fresh café rituals, made easy/);
  assert.doesNotMatch(home, />Coffee bar</);
  assert.doesNotMatch(home, /Seasonal pours, bakery favorites, and quiet coffee bar classics/);
  assert.doesNotMatch(home, /className="cafe-hero-image"/);
  assert.doesNotMatch(home, /\{coffeeCount\} crafted drinks/);
  assert.doesNotMatch(home, /<div className="welcome-actions">/);
});

test("Home hero fills and crops the artwork responsively without distortion", () => {
  assert.match(styles, /\.home-page \.app-welcome-panel \{[\s\S]*?align-items:\s*center;[\s\S]*?justify-content:\s*center;/);
  assert.match(styles, /Ladel's customer hero and navigation branding[\s\S]*?\.home-page \.app-welcome-panel \{[\s\S]*?aspect-ratio:\s*3 \/ 1;[\s\S]*?padding:\s*0;/);
  assert.match(styles, /Ladel's customer hero and navigation branding[\s\S]*?\.home-page \.ladels-hero-logo \{[\s\S]*?width:\s*100%;[\s\S]*?height:\s*100%;[\s\S]*?object-fit:\s*cover;[\s\S]*?object-position:\s*50% 53%;[\s\S]*?transform:\s*scale\(1\.04\)/);
  assert.doesNotMatch(styles.slice(styles.indexOf("Ladel's customer hero and navigation branding")), /object-fit:\s*contain/);
  assert.match(styles, /@media \(min-width: 761px\) \{[\s\S]*?\.home-page \.app-welcome-panel \{[\s\S]*?padding:\s*0;[\s\S]*?\.home-page \.ladels-hero-logo \{[\s\S]*?object-position:\s*50% 53%;[\s\S]*?transform:\s*scale\(1\.04\)/);
  assert.match(styles, /@media \(max-width: 760px\) \{[\s\S]*?\.site-header \{[\s\S]*?display:\s*none;[\s\S]*?\.home-page,[\s\S]*?\.page-section \{[\s\S]*?padding-top:\s*max\(14px, env\(safe-area-inset-top\)\);[\s\S]*?\.home-page \.app-welcome-panel \{[\s\S]*?aspect-ratio:\s*2\.55 \/ 1;[\s\S]*?padding:\s*0;[\s\S]*?\.home-page \.ladels-hero-logo \{[\s\S]*?object-position:\s*48% 54%;[\s\S]*?transform:\s*scale\(1\.1\)/);
});

test("customer header removes legacy branding and preserves navigation", async () => {
  const layout = await readFile(new URL("../../src/layouts/AppLayout.jsx", import.meta.url), "utf8");
  for (const label of ["Home", "Browse", "Cart", "Account"]) {
    assert.match(layout, new RegExp(`label: "${label}"`));
  }
  assert.doesNotMatch(layout, /className="brand"/);
  assert.doesNotMatch(layout, /className="brand-mark"/);
  assert.doesNotMatch(layout, /guestHouseLogo/);
  assert.doesNotMatch(layout, />The Guest House</);
  assert.doesNotMatch(layout, />Café & Pantry</);
  assert.match(layout, /className="nav-container customer-nav-container"/);
  assert.match(layout, /aria-label="Desktop ordering navigation"/);
  assert.match(layout, /aria-label="Mobile ordering navigation"/);
  assert.doesNotMatch(layout, /className="header-cart-link"/);
  assert.doesNotMatch(layout, /aria-label="Open cart"/);
});

test("Home keeps the café bag Cart link and live quantity summary", () => {
  assert.match(home, /className="home-order-status" aria-live="polite"/);
  assert.match(home, /"Your café bag"/);
  assert.match(home, /<Link to="\/cart">/);
  assert.match(home, /cart\.reduce\(\(total, item\) => total \+ item\.quantity, 0\)/);
  assert.match(home, /\{cartCount\} \{cartCount === 1 \? "item" : "items"\} · \{formatPrice\(cartTotal\)\}/);
});
