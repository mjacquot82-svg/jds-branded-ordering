import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { filterStarterMedia, starterCategoryLabel, starterPreviewUrl, suggestedStarterMedia } from "../../src/services/starterMedia.js";

const assets = [
  { key: "latte", name: "Latte", tags: ["latte", "vanilla", "caramel", "milk", "coffee"], category: "coffee", sortOrder: 40 },
  { key: "cappuccino", name: "Cappuccino", tags: ["cappuccino", "oat", "milk", "coffee"], category: "coffee", sortOrder: 50 },
  { key: "flat-white-cortado", name: "Flat white or cortado", tags: ["flat", "white", "cortado"], category: "coffee", sortOrder: 60 },
  { key: "iced-latte", name: "Iced latte", tags: ["iced", "latte", "caramel", "coffee"], category: "coffee", sortOrder: 80 },
  { key: "chai-latte", name: "Chai latte", tags: ["chai", "tea", "milk"], category: "tea-specialty-drinks", sortOrder: 120 },
  { key: "matcha-latte", name: "Matcha latte", tags: ["matcha", "tea", "milk"], category: "tea-specialty-drinks", sortOrder: 130 },
  { key: "breakfast-sandwich", name: "Breakfast sandwich", tags: ["egg", "bacon", "english", "muffin"], category: "breakfast", sortOrder: 220 },
  { key: "muffin", name: "Muffin", tags: ["blueberry", "bran", "bakery"], category: "bakery", sortOrder: 340 },
  { key: "scone", name: "Scone", tags: ["blueberry", "bakery"], category: "bakery", sortOrder: 350 },
  { key: "brownie-dessert-square", name: "Brownie or dessert square", tags: ["brownie", "chocolate"], category: "bakery", sortOrder: 370 },
  { key: "deli-sandwich", name: "Deli-style sandwich", tags: ["blt", "club", "turkey", "ham"], category: "sandwiches-wraps", sortOrder: 430 },
  { key: "panini-grilled-sandwich", name: "Panini or grilled sandwich", tags: ["panini", "grilled"], category: "sandwiches-wraps", sortOrder: 450 },
  { key: "wrap", name: "Wrap", tags: ["chicken", "caesar", "lunch"], category: "sandwiches-wraps", sortOrder: 460 },
  { key: "chili", name: "Chili", tags: ["chili", "stew", "beans"], category: "soup-salad", sortOrder: 560 },
  { key: "composed-salad", name: "Composed salad", tags: ["caesar", "cobb", "chicken"], category: "soup-salad", sortOrder: 580 },
  { key: "cheesecake", name: "Cheesecake", tags: ["cheesecake", "dessert"], category: "desserts", sortOrder: 620 },
  { key: "coffee-beans-bag", name: "Bag of coffee beans", tags: ["coffee", "beans", "retail"], category: "packaged-retail", sortOrder: 680 },
];

test("starter suggestions are deterministic and exact product terms rank first", () => {
  assert.equal(suggestedStarterMedia(assets, "Latte")[0].key, "latte");
  assert.equal(suggestedStarterMedia(assets, "Caramel latte")[0].key, "latte");
  assert.equal(suggestedStarterMedia(assets, "Iced caramel latte")[0].key, "iced-latte");
  assert.equal(suggestedStarterMedia(assets, "Cortado")[0].key, "flat-white-cortado");
  assert.equal(suggestedStarterMedia(assets, "Chai")[0].key, "chai-latte");
  assert.equal(suggestedStarterMedia(assets, "Matcha")[0].key, "matcha-latte");
  assert.equal(suggestedStarterMedia(assets, "Bacon Egg English Muffin")[0].key, "breakfast-sandwich");
  assert.equal(suggestedStarterMedia(assets, "BLT")[0].key, "deli-sandwich");
  assert.equal(suggestedStarterMedia(assets, "Panini")[0].key, "panini-grilled-sandwich");
  assert.equal(suggestedStarterMedia(assets, "Chicken Caesar Wrap")[0].key, "wrap");
  assert.equal(suggestedStarterMedia(assets, "Oat Milk Cappuccino")[0].key, "cappuccino");
  for (const [query, expected] of [
    ["Muffin", "muffin"], ["Scone", "scone"], ["Brownie", "brownie-dessert-square"],
    ["Chili", "chili"], ["Caesar salad", "composed-salad"],
    ["Cheesecake", "cheesecake"], ["Coffee beans", "coffee-beans-bag"],
  ]) assert.equal(suggestedStarterMedia(assets, query)[0].key, expected);
  assert.deepEqual(suggestedStarterMedia(assets, "House special"), []);
});

test("starter browsing filters metadata without loading image binaries", () => {
  assert.ok(filterStarterMedia(assets, { query: "coffee beans" }).some((asset) => asset.key === "coffee-beans-bag"));
  assert.deepEqual(filterStarterMedia(assets, { category: "desserts" }).map((asset) => asset.key), ["cheesecake"]);
  assert.equal(starterCategoryLabel("tea-specialty-drinks"), "Tea & Specialty Drinks");
  assert.equal(starterPreviewUrl("starter:cafe-restaurant/latte@1"), "/api/v1/storefront/starter-media/cafe-restaurant/latte?version=1");
});

test("product editor keeps platform starters, tenant media, and upload as distinct sources", async () => {
  const page = await readFile(new URL("../../src/admin/ProductsPage.jsx", import.meta.url), "utf8");
  assert.match(page, />Choose a starter image</);
  assert.match(page, /"Upload my own"/);
  assert.match(page, />Choose from my images</);
  assert.match(page, /JDS starter image selected/);
  assert.match(page, /Image coming soon/);
  assert.match(page, /disabled=\{!asset\.available\}/);
  assert.match(page, /loading="lazy"/);
  assert.doesNotMatch(page, /storageKey/);
});
