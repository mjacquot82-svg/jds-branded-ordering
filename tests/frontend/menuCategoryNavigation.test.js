import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { resolveMenuCategory } from "../../src/services/menuCatalog.js";

const home = await readFile(new URL("../../src/pages/HomePage.jsx", import.meta.url), "utf8");
const menu = await readFile(new URL("../../src/pages/MenuPage.jsx", import.meta.url), "utf8");

test("Home category cards deep-link with each stable category slug", () => {
  assert.match(home, /category\.slug/);
  assert.match(home, /encodeURIComponent\(category\.slug\)/);
  assert.match(home, /\/menu\?category=/);

  const destination = (slug) => `/menu?category=${encodeURIComponent(slug)}`;
  assert.equal(destination("smoothies"), "/menu?category=smoothies");
  assert.equal(destination("coffee"), "/menu?category=coffee");
  assert.equal(destination("cold-drinks"), "/menu?category=cold-drinks");
});

test("Browse derives category selection from URL state on every render", () => {
  assert.match(menu, /searchParams\.get\("category"\)/);
  assert.match(menu, /resolveMenuCategory\(sections, categorySlug, targetProduct\)/);
  assert.doesNotMatch(menu, /useState\(firstSection\)/);
});

test("Browse category changes create Back-Forward-compatible category URLs", () => {
  assert.match(menu, /setSearchParams\(\{ category: section\.id \}\)/);
  assert.doesNotMatch(menu, /setSearchParams\(\{ category: section\.id \}, \{ replace: true \}\)/);
});

test("Browse clears obsolete product spotlight when selecting a category", () => {
  assert.match(menu, /setSpotlightProductId\(""\)/);
  assert.match(menu, /setExpandedProductId\(""\)/);
  assert.match(menu, /setSearchParams\(\{ category: section\.id \}\)/);
});

test("invalid categories are canonicalized with replace while plain menu stays plain", () => {
  assert.match(menu, /if \(status !== "ready" \|\| targetProduct \|\| !categorySlug\)/);
  assert.match(menu, /setSearchParams\(activeSectionId \? \{ category: activeSectionId \} : \{\}, \{ replace: true \}\)/);
});

test("product deep links derive the target product category and stale products safely fall back", () => {
  const sections = [
    { id: "coffee", items: [{ id: "drip-coffee" }] },
    { id: "meals", items: [{ id: "buffalo-chickpea-bowl" }] },
  ];
  const lunchSpecial = { id: "buffalo-chickpea-bowl", category: "meals", available: true };

  assert.equal(resolveMenuCategory(sections, "coffee", lunchSpecial), "meals");
  assert.equal(resolveMenuCategory(sections, "", undefined), "coffee");
  assert.match(menu, /searchParams\.get\("product"\)/);
  assert.match(menu, /product\.id === targetProductId && product\.available/);
  assert.match(menu, /setExpandedProductId\(targetProduct\.id\)/);
  assert.match(menu, /scrollIntoView\(\{ behavior: "smooth", block: "center" \}\)/);
  assert.match(menu, /productCard\.focus\(\{ preventScroll: true \}\)/);
  assert.match(menu, /setSpotlightProductId\(targetProduct\.id\)/);
});
