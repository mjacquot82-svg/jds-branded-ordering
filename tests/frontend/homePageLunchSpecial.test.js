import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(new URL("../../src/pages/HomePage.jsx", import.meta.url), "utf8");

test("homepage keeps lunch promotion distinct from restored quick ordering", () => {
  assert.doesNotMatch(home, /Order a favorite/);
  assert.match(home, /quick-product-rail/);
  assert.match(home, /Today’s Lunch Special/);
  assert.match(home, /Order Today’s Special/);
  assert.match(home, /recommendation\.description/);
  assert.match(home, /getConfiguredPrice\(recommendation/);
  assert.match(home, /`\/menu\?product=\$\{encodeURIComponent\(recommendation\.id\)\}`/);
});

test("homepage removes compact favorites and renders a complete fallback", () => {
  assert.doesNotMatch(home, /Café favorites/);
  assert.doesNotMatch(home, /cafe-favorites-block/);
  assert.match(home, /Today’s Picks/);
  assert.match(home, /Browse today’s menu/);
  assert.match(home, /Something delicious is always waiting/);
});

test("homepage grid prioritizes lunch before browse and quick order", async () => {
  const styles = await readFile(new URL("../../src/style.css", import.meta.url), "utf8");
  const lunchStyles = styles.match(/\.home-page \.lunch-special-block \{[\s\S]*?\}/g) || [];

  assert.ok(lunchStyles.length >= 2);
  assert.match(lunchStyles.join("\n"), /grid-column:\s*1\s*\/\s*-1/);
  assert.match(styles, /\.home-page\.ordering-page \{[\s\S]*?grid-template-columns:/);
  assert.match(styles, /\.home-page \.home-category-block \{ grid-column: 1; \}/);
  assert.match(styles, /\.home-page \.quick-add-block \{ grid-column: 2; \}/);
  assert.match(styles, /\.home-page \.loyalty-card \{ grid-column: 1 \/ -1; \}/);
  assert.ok(home.indexOf("lunch-special-block") < home.indexOf("home-category-block"));
  assert.ok(home.indexOf("home-category-block") < home.indexOf("quick-add-block"));
});

test("category browser retains a stable place through catalog states", () => {
  assert.match(home, /Preparing the café menu/);
  assert.match(home, /Browse the full café menu/);
  assert.match(home, /Today’s menu is being prepared/);
  assert.match(home, /category-pill-grid/);
  assert.match(home, /to=\{`\/menu\?category=\$\{encodeURIComponent\(category\.slug\)\}`\}/);
});

test("Home distinguishes unresolved, unavailable, and genuinely empty catalog states", () => {
  assert.match(home, /Loading today’s special…/);
  assert.match(home, /Today’s special is temporarily unavailable/);
  assert.match(home, /onClick=\{reload\}>Try again/);
});

test("Quick Order makes generic cards configuration links and reserves direct Add for exact configurations", () => {
  assert.match(home, /Quick Order/);
  assert.match(home, /quick-product-rail/);
  assert.match(home, /quick-product-card/);
  assert.match(home, /Order your usual/);
  assert.match(home, /addQuickItem/);
  assert.match(home, /storeCart/);
  assert.match(home, /const QuickOrderCard = item\.quickConfiguration \? "article" : Link/);
  assert.match(home, /"aria-label": `Customize \$\{item\.name\}`/);
  assert.match(home, /Order your usual \$\{item\.name\}/);
  assert.match(home, /title="Order this exact configuration"/);
  assert.match(home, /<span>Order<\/span>/);
  assert.doesNotMatch(home, /<span>Add<\/span>/);
  assert.match(home, /\{item\.quickConfiguration \? <button/);
  assert.doesNotMatch(home, />Customize<\/Link>/);
  assert.match(home, /getProductSpecificImageUrl\(item\)/);
  assert.match(home, /productImageUrl \? \(/);
  assert.doesNotMatch(home, /item-thumb-\$\{item\.image\}/);
});

test("customer button interaction states preserve foreground contrast", async () => {
  const styles = await readFile(new URL("../../src/style.css", import.meta.url), "utf8");

  assert.match(styles, /Customer interaction-state foreground safety/);
  assert.match(styles, /\.ordering-page \.primary-button:not\(:disabled\)[\s\S]*?color:\s*#fffdf8;[\s\S]*?-webkit-text-fill-color:\s*#fffdf8/);
  assert.match(styles, /\.ordering-page \.drink-card button:not\(:disabled\):is\(:active, :focus, :focus-visible, \[aria-pressed="true"\], \.active, \.selected, \.is-added\)/);
  assert.match(styles, /\.home-page \.quick-product-card button:not\(:disabled\):is\(:active, :focus, :focus-visible, \[aria-pressed="true"\]\)/);
  assert.match(styles, /\.ordering-page \.secondary-button:not\(:disabled\)[\s\S]*?color:\s*var\(--gh-charcoal\);[\s\S]*?-webkit-text-fill-color:\s*var\(--gh-charcoal\)/);
  assert.match(styles, /\.home-page a\.quick-product-card:is\(:active, :focus, :focus-visible\)/);
});

test("expanded Browse option toggle stays light-on-dark without changing light controls", async () => {
  const styles = await readFile(new URL("../../src/style.css", import.meta.url), "utf8");

  assert.match(styles, /\.app-menu-page \.product-customize-toggle\[aria-expanded="true"\]:not\(:disabled\)/);
  assert.match(styles, /\.app-menu-page \.drink-card \.product-customize-toggle,[\s\S]*?\.app-menu-page \.drink-card \.product-customize-toggle:hover,[\s\S]*?\.app-menu-page \.drink-card \.product-customize-toggle:active,[\s\S]*?color:\s*#fffdf8;[\s\S]*?-webkit-text-fill-color:\s*#fffdf8/);
  assert.match(styles, /\.app-menu-page \.drink-card \.product-customize-toggle\[aria-expanded="true"\] \{[\s\S]*?background:\s*#4c5a40/);
  assert.match(styles, /\.app-menu-page \.drink-card \.product-customize-toggle\[aria-expanded="true"\]:is\(:hover, :active, :focus, :focus-visible\) \{[\s\S]*?background:\s*#3f4d35/);
  assert.match(styles, /\.app-menu-page \.product-customize-toggle:not\(:disabled\):is\(:active, :focus, :focus-visible\)/);
  assert.match(styles, /\.app-menu-page \.drink-card \.product-customize-toggle:focus-visible \{[\s\S]*?outline:\s*3px solid[\s\S]*?outline-offset:\s*2px/);
  assert.doesNotMatch(styles, /\.ordering-page \.secondary-button:not\(:disabled\),\s*\.ordering-page \.product-customize-toggle/);
  assert.match(styles, /\.ordering-page \.secondary-button:not\(:disabled\)[\s\S]*?color:\s*var\(--gh-charcoal\)/);
  assert.match(styles, /\.ordering-page \.quantity-stepper button:not\(:disabled\)[\s\S]*?color:\s*var\(--gh-charcoal\)/);
});

test("image-less lunch specials never inherit generic product photography", async () => {
  const styles = await readFile(new URL("../../src/style.css", import.meta.url), "utf8");

  assert.match(home, /getProductSpecificImageUrl\(recommendation\)/);
  assert.match(home, /recommendationImageUrl \? \(/);
  assert.doesNotMatch(home, /item-thumb-\$\{recommendation\.image\}/);
  assert.doesNotMatch(home, /Browse today’s café menu for fresh, seasonal recommendations/);
  assert.match(styles, /\.lunch-special-block\.is-image-free/);
});

test("mobile lunch special is compact and text-safe", async () => {
  const styles = await readFile(new URL("../../src/style.css", import.meta.url), "utf8");

  assert.match(styles, /\.home-page \.lunch-special-copy \{[\s\S]*?min-width:\s*0/);
  assert.match(styles, /\.home-page \.lunch-special-copy h3 \{[\s\S]*?overflow-wrap:\s*anywhere/);
  assert.match(styles, /\.home-page \.lunch-special-copy \{[\s\S]*?padding:\s*16px/);
});
