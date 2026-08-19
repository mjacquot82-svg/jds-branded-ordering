import assert from "node:assert/strict";
import { after, test } from "node:test";
import { readFileSync } from "node:fs";

import { JSDOM } from "jsdom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const vite = await createServer({ appType: "custom", server: { hmr: false, middlewareMode: true } });
const [{ default: App }, { CustomerAuthProvider }] = await Promise.all([
  vite.ssrLoadModule("/src/App.jsx"),
  vite.ssrLoadModule("/src/auth/CustomerAuthContext.jsx"),
]);

after(() => vite.close());

const option = (id, key, name, price, sortOrder) => ({
  id, key, name, price_cents: price, sort_order: sortOrder,
});

const catalog = {
  version: "1",
  generated_at: "2026-08-11T00:00:00Z",
  pricing: { tax_name: "HST", tax_rate_millionths: 130000 },
  categories: [{
    id: "10", slug: "coffee", name: "Coffee", note: "House cups.", sort_order: 0,
    products: [
      {
        id: "100", slug: "granola-yogurt", name: "Granola Yogurt", description: "Ready to enjoy.", image: "", featured: false, lunch_special: false, base_price_cents: 550, sort_order: 0, variants: [], modifier_groups: [],
      },
      {
        id: "101", slug: "drip-coffee", name: "House Coffee", description: "Fresh brewed.", image: "", featured: true, lunch_special: false, base_price_cents: 205, sort_order: 1,
        variants: [option("1001", "12oz", "12oz", 205, 0), option("1002", "16oz", "16oz", 240, 1), option("1003", "20oz", "20oz", 275, 2)], modifier_groups: [],
      },
      {
        id: "102", slug: "latte", name: "Latte", description: "Espresso and milk.", image: "", featured: true, lunch_special: false, base_price_cents: 445, sort_order: 2,
        variants: [option("2001", "12oz", "12oz", 445, 0), option("2002", "20oz", "20oz", 565, 1)],
        modifier_groups: [{
          id: "300", key: "milk", name: "Milk", description: "", selection_type: "single", required: false, min_selections: 0, max_selections: 1, sort_order: 0,
          options: [
            { id: "3001", key: "whole", name: "Whole milk", price_adjustment_cents: 0, sort_order: 0 },
            { id: "3002", key: "oat", name: "Oat", price_adjustment_cents: 85, sort_order: 1 },
          ],
        }],
      },
      {
        id: "103", slug: "decaf-coffee", name: "Drip Coffee", description: "Fresh brewed decaf.", image: "", featured: false, lunch_special: false, base_price_cents: 205, sort_order: 3,
        variants: [option("4001", "16oz", "16oz", 240, 0)],
        modifier_groups: [
          {
            id: "401", key: "milk", name: "Milk", description: "", selection_type: "single", required: false, min_selections: 0, max_selections: 1, allow_quantity: false, sort_order: 0,
            options: [{ id: "4011", key: "oat", name: "Oat", price_adjustment_cents: 85, sort_order: 0 }],
          },
          {
            id: "402", key: "sugar", name: "Sugar", description: "", selection_type: "single", required: false, min_selections: 0, max_selections: 3, allow_quantity: true, sort_order: 1,
            options: [
              { id: "4021", key: "sugar", name: "Sugar", price_adjustment_cents: 0, sort_order: 0 },
              { id: "4022", key: "sweetener", name: "Sweetener", price_adjustment_cents: 0, sort_order: 1 },
            ],
          },
          {
            id: "403", key: "flavour-shots", name: "Flavour shots", description: "", selection_type: "multiple", required: true, min_selections: 1, max_selections: 3, allow_quantity: true, sort_order: 2,
            options: [
              { id: "4031", key: "vanilla", name: "Vanilla", price_adjustment_cents: 75, sort_order: 0 },
              { id: "4032", key: "caramel", name: "Caramel", price_adjustment_cents: 75, sort_order: 1 },
              { id: "4033", key: "hazelnut", name: "Hazelnut", price_adjustment_cents: 75, sort_order: 2 },
            ],
          },
        ],
      },
    ],
  }],
};

const response = (status, payload) => ({ json: async () => payload, ok: status >= 200 && status < 300, status });

async function waitForText(container, text) {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (container.textContent.includes(text)) return;
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
  }
  assert.fail(`Expected ${text}; rendered: ${container.textContent}`);
}

async function click(element, window) {
  assert.ok(element);
  await act(async () => element.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true })));
}

test("customer configures real choice shapes, gets readable success feedback, and reviews selections in Cart", { concurrency: false }, async () => {
  const dom = new JSDOM("<div id=\"root\"></div>", { url: "https://cafe.test/menu?product=decaf-coffee" });
  const previous = { document: globalThis.document, fetch: globalThis.fetch, localStorage: globalThis.localStorage, navigator: globalThis.navigator, requestAnimationFrame: globalThis.requestAnimationFrame, window: globalThis.window };
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.localStorage = dom.window.localStorage;
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
  globalThis.requestAnimationFrame = (callback) => callback();
  let scrolledProductId = "";
  dom.window.HTMLElement.prototype.scrollIntoView = function scrollIntoView() { scrolledProductId = this.id; };
  const style = document.createElement("style");
  style.textContent = readFileSync(new URL("../../src/style.css", import.meta.url), "utf8");
  document.head.append(style);
  globalThis.fetch = async (url) => {
    const path = new URL(String(url), "https://cafe.test").pathname;
    if (path === "/api/v1/catalog") return response(200, catalog);
    if (path === "/api/v1/customer/auth/session") return response(401, { detail: { code: "authentication_required" } });
    if (path === "/api/v1/scheduling/options") return response(200, { ordering_available: true, quick_pickup_options: [{ key: "asap", label: "ASAP", preference_minutes: null, requested_pickup_at: "2026-08-11T12:30:00Z" }], minimum_lead_time_minutes: 10, pickup_interval_minutes: 5, maximum_advance_days: 1, business_timezone: "UTC", custom_pickup_at: null, custom_pickup_error: null });
    throw new Error(`Unexpected request: ${path}`);
  };

  const root = createRoot(document.getElementById("root"));
  try {
    await act(async () => root.render(React.createElement(MemoryRouter, { initialEntries: ["/menu?product=decaf-coffee"] }, React.createElement(CustomerAuthProvider, null, React.createElement(App)))));
    await waitForText(document.body, "House Coffee");

    const card = (name) => [...document.querySelectorAll(".app-product-card")].find((item) => item.textContent.includes(name));
    const deepLinked = document.getElementById("product-decaf-coffee");
    assert.equal(document.querySelector(".menu-category-rail button.active").textContent, "Coffee");
    assert.equal(deepLinked.classList.contains("is-expanded"), true);
    assert.equal(deepLinked.classList.contains("is-spotlighted"), true);
    assert.equal(deepLinked.querySelector('.product-customize-toggle').getAttribute("aria-expanded"), "true");
    assert.equal(scrolledProductId, "product-decaf-coffee");
    assert.equal(document.activeElement, deepLinked);
    assert.equal(deepLinked.querySelector(".product-add-button").disabled, true);
    assert.match(deepLinked.textContent, /\$2\.05/);
    assert.equal(localStorage.getItem("cafe-cart"), null);
    const direct = card("Granola Yogurt");
    assert.equal(direct.querySelector(".product-customization"), null);
    await click(direct.querySelector(".product-add-button"), dom.window);

    const drip = card("House Coffee");
    const dripAdd = drip.querySelector(".product-add-button");
    assert.equal(drip.querySelector("legend").textContent, "Size (required)");
    assert.equal(dripAdd.disabled, true);
    assert.equal(dripAdd.textContent, "Choose Size");
    await click([...drip.querySelectorAll("label")].find((label) => label.textContent.includes("16oz")), dom.window);
    assert.equal(dripAdd.disabled, false);
    assert.match(drip.textContent, /\$2\.40/);
    await click(dripAdd, dom.window);
    assert.equal(dripAdd.textContent, "Added — Add another");
    assert.equal(dripAdd.classList.contains("is-added"), true);
    assert.equal(dripAdd.disabled, false);
    const addedStyle = dom.window.getComputedStyle(dripAdd);
    const addedTextStyle = dom.window.getComputedStyle(dripAdd.querySelector("span"));
    assert.equal(addedStyle.backgroundColor, "rgb(25, 69, 39)");
    assert.equal(addedStyle.color, "rgb(255, 255, 255)");
    assert.equal(addedStyle.opacity, "1");
    assert.equal(addedTextStyle.opacity, "1");
    assert.equal(addedTextStyle.webkitTextFillColor, "rgb(255, 255, 255)");
    assert.match(drip.textContent, /1 in cart/);

    const latte = card("Latte");
    const latteToggle = latte.querySelector(".product-customize-toggle");
    assert.equal(latteToggle.textContent, "Customize");
    assert.equal(latteToggle.getAttribute("aria-expanded"), "false");
    assert.equal(dom.window.getComputedStyle(latteToggle).color, "rgb(255, 253, 248)");
    await click(latteToggle, dom.window);
    assert.equal(latteToggle.textContent, "Collapse options");
    assert.equal(latteToggle.getAttribute("aria-expanded"), "true");
    const expandedToggleStyle = dom.window.getComputedStyle(latteToggle);
    assert.equal(expandedToggleStyle.color, "rgb(255, 253, 248)");
    assert.equal(expandedToggleStyle.webkitTextFillColor, "rgb(255, 253, 248)");
    latteToggle.focus();
    assert.equal(dom.window.document.activeElement, latteToggle);
    assert.equal(dom.window.getComputedStyle(latteToggle).color, "rgb(255, 253, 248)");
    await click(latteToggle, dom.window);
    assert.equal(latteToggle.textContent, "Customize");
    assert.equal(latteToggle.getAttribute("aria-expanded"), "false");
    await click(latteToggle, dom.window);
    assert.equal(latteToggle.textContent, "Collapse options");
    await click([...latte.querySelectorAll("label")].find((label) => label.textContent.includes("20oz")), dom.window);
    await click([...latte.querySelectorAll("label")].find((label) => label.textContent.includes("Oat")), dom.window);
    assert.match(latte.textContent, /\$6\.50/);
    await click(latte.querySelector(".product-add-button"), dom.window);

    const decaf = card("Drip Coffee");
    const sugarOutput = decaf.querySelector('[aria-label="Sugar quantity"] output');
    const sugarPlus = decaf.querySelector('button[aria-label="Add one Sugar"]');
    const sugarMinus = decaf.querySelector('button[aria-label="Remove one Sugar"]');
    const sweetenerPlus = decaf.querySelector('button[aria-label="Add one Sweetener"]');
    const noSugar = [...decaf.querySelectorAll("label")].find((label) => label.textContent.includes("No sugar"));
    const decafAdd = decaf.querySelector(".product-add-button");
    assert.equal(sugarOutput.textContent, "0");
    assert.equal(noSugar.querySelector("input").checked, false);
    assert.equal(decafAdd.disabled, true);
    await click(sugarPlus, dom.window);
    assert.equal(sugarOutput.textContent, "1");
    assert.equal(sweetenerPlus.disabled, true);
    await click(sugarPlus, dom.window);
    assert.equal(sugarOutput.textContent, "2");
    await click(sugarMinus, dom.window);
    assert.equal(sugarOutput.textContent, "1");
    await click(sugarMinus, dom.window);
    assert.equal(sugarOutput.textContent, "0");
    assert.equal(sweetenerPlus.disabled, false);
    assert.equal(decafAdd.disabled, true);
    await click(noSugar, dom.window);
    assert.equal(noSugar.querySelector("input").checked, true);
    await click(sugarPlus, dom.window);
    assert.equal(noSugar.querySelector("input").checked, false);
    await click(sugarPlus, dom.window);
    await click(noSugar, dom.window);
    assert.equal(sugarOutput.textContent, "0");
    await click(sugarPlus, dom.window);
    await click(sugarPlus, dom.window);
    await click(sugarPlus, dom.window);
    assert.equal(sugarPlus.disabled, true);
    await click(sugarMinus, dom.window);
    assert.equal(sugarOutput.textContent, "2");

    await click([...decaf.querySelectorAll("label")].find((label) => label.textContent.includes("16oz")), dom.window);
    const noMilk = [...decaf.querySelectorAll("label")].find((label) => label.textContent.includes("No milk"));
    assert.equal(noMilk.querySelector("input").type, "radio");
    assert.equal(decaf.querySelector('[aria-label="Oat quantity"]'), null);
    await click(noMilk, dom.window);
    const vanillaPlus = decaf.querySelector('button[aria-label="Add one Vanilla"]');
    const caramelPlus = decaf.querySelector('button[aria-label="Add one Caramel"]');
    assert.equal(dom.window.getComputedStyle(vanillaPlus).color, "rgb(255, 253, 248)");
    const flavourGroup = [...decaf.querySelectorAll("fieldset")].find((group) => group.textContent.includes("Flavour shots"));
    assert.ok(document.querySelectorAll(".app-product-card").length > 1);
    assert.equal(flavourGroup.querySelector("legend").textContent, "Flavour shots (required)");
    assert.equal([...flavourGroup.querySelectorAll("label")].some((label) => label.textContent.includes("No flavour")), false);
    assert.deepEqual([...flavourGroup.querySelectorAll(".modifier-quantity-row > span")].map((name) => name.textContent), ["Vanilla", "Caramel", "Hazelnut"]);
    assert.equal(flavourGroup.querySelector(".modifier-options").children.length, 3);
    assert.ok([...flavourGroup.querySelectorAll(".modifier-quantity-row")].every((row) => row.parentElement.classList.contains("modifier-options")));
    assert.equal(flavourGroup.querySelectorAll("small").length, 3);
    assert.equal(flavourGroup.querySelectorAll("small")[0].textContent, "+$0.75 each");
    await click(vanillaPlus, dom.window);
    await click(vanillaPlus, dom.window);
    await click(caramelPlus, dom.window);
    assert.equal(vanillaPlus.disabled, true);
    assert.equal(caramelPlus.disabled, true);
    assert.equal(decafAdd.disabled, false);
    assert.match(decaf.textContent, /\$4\.65/);
    await click(decafAdd, dom.window);

    const stored = JSON.parse(localStorage.getItem("cafe-cart"));
    assert.deepEqual(stored.map((item) => item.id), [
      "granola-yogurt",
      "drip-coffee__size:16oz",
      "latte__milk:oat|size:20oz",
      "decaf-coffee__flavour-shots:caramel|flavour-shots:vanilla:2|size:16oz|sugar:sugar:2",
    ]);
    const decafCart = stored.find((item) => item.productId === "decaf-coffee");
    assert.equal(decafCart.price, 4.65);
    assert.deepEqual(decafCart.options.map(({ name, quantity }) => [name, quantity]), [
      ["16oz", 1], ["Sugar", 2], ["Vanilla", 2], ["Caramel", 1],
    ]);
    assert.equal(decafCart.options.some((item) => item.name.startsWith("No ")), false);
    const viewCart = [...document.querySelectorAll("a")].find((link) => link.textContent === "View cart");
    const viewCartStyle = dom.window.getComputedStyle(viewCart);
    assert.equal(viewCartStyle.color, "rgb(255, 253, 248)");
    await click(viewCart, dom.window);
    await waitForText(document.body, "Your order");
    assert.match(document.body.textContent, /Size: 16oz/);
    assert.match(document.body.textContent, /Size: 20oz · Milk: Oat/);
    assert.match(document.body.textContent, /Sugar x2/);
    assert.match(document.body.textContent, /Vanilla x2/);
    assert.match(document.body.textContent, /Flavour shots: Vanilla x2, Caramel/);
    assert.doesNotMatch(document.body.textContent, /Flavour shots: Vanilla x2[^·]*Flavour shots: Caramel/);
    assert.match(document.body.textContent, /\$6\.50/);

    await click([...document.querySelectorAll("a")].find((link) => link.textContent.trim() === "Home"), dom.window);
    await waitForText(document.body, "Quick Order");
    assert.equal(document.querySelector('button[aria-label="Quick add House Coffee"]'), null);
    assert.ok(document.querySelector('a[aria-label="Customize House Coffee"]'));
    await click([...document.querySelectorAll("a")].find((link) => link.textContent.includes("Coffee") && link.getAttribute("href")?.includes("category=coffee")), dom.window);
    await waitForText(document.body, "Crafted drinks and fresh bites");
    assert.equal(document.querySelector(".menu-category-rail button.active").textContent, "Coffee");
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
    globalThis.window = previous.window;
    globalThis.document = previous.document;
    globalThis.fetch = previous.fetch;
    globalThis.localStorage = previous.localStorage;
    globalThis.requestAnimationFrame = previous.requestAnimationFrame;
    Object.defineProperty(globalThis, "navigator", { configurable: true, value: previous.navigator });
  }
});
