import assert from "node:assert/strict";
import { after, test } from "node:test";

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

const response = (status, payload) => ({ json: async () => payload, ok: status >= 200 && status < 300, status });
const catalog = {
  version: "1", generated_at: "2026-08-12T00:00:00Z",
  pricing: { tax_name: "HST", tax_rate_millionths: 1_300_000 },
  categories: [{
    id: "10", slug: "coffee", name: "Coffee", note: "", sort_order: 0,
    products: [{
      id: "101", slug: "coffee", name: "Coffee", description: "", image: "",
      featured: false, lunch_special: false, base_price_cents: 300, sort_order: 0,
      variants: [{ id: "1001", key: "large", name: "Large", price_cents: 400, sort_order: 0 }],
      modifier_groups: [{
        id: "200", key: "sugar", name: "Sugar", description: "",
        selection_type: "single", required: false, min_selections: 0,
        max_selections: 3, allow_quantity: true, sort_order: 0,
        options: [{ id: "2001", key: "sugar", name: "Sugar", price_adjustment_cents: 25, sort_order: 0 }],
      }],
    }],
  }],
};
const configuredCart = [{
  id: "coffee__size:large|sugar:sugar:2", productId: "coffee", productBackendId: "101",
  name: "Coffee", description: "", category: "coffee", basePrice: 3, price: 4.5,
  quantity: 3, options: [
    { groupId: "size", groupName: "Size", name: "Large", variantId: "1001", priceDelta: 1, quantity: 1 },
    { backendId: "2001", groupId: "sugar", groupName: "Sugar", name: "Sugar", priceDelta: 0.25, quantity: 2 },
  ],
}];

async function waitForText(container, text) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (container.textContent.includes(text)) return;
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
  }
  assert.fail(`Expected ${text}; rendered: ${container.textContent}`);
}

async function click(element, window) {
  assert.ok(element);
  await act(async () => element.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true })));
}

async function input(element, value, window) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(element, value);
  await act(async () => {
    element.dispatchEvent(new window.Event("input", { bubbles: true }));
    element.dispatchEvent(new window.Event("change", { bubbles: true }));
  });
}

async function submit(form, window) {
  await act(async () => form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })));
}

async function runContinuation(mode) {
  const dom = new JSDOM('<div id="root"></div>', { url: "https://cafe.test/cart" });
  const previous = { document: globalThis.document, fetch: globalThis.fetch, localStorage: globalThis.localStorage, navigator: globalThis.navigator, requestAnimationFrame: globalThis.requestAnimationFrame, sessionStorage: globalThis.sessionStorage, window: globalThis.window };
  globalThis.window = dom.window; globalThis.document = dom.window.document;
  globalThis.localStorage = dom.window.localStorage; globalThis.sessionStorage = dom.window.sessionStorage;
  globalThis.requestAnimationFrame = (callback) => callback();
  dom.window.requestAnimationFrame = globalThis.requestAnimationFrame;
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
  localStorage.setItem("cafe-cart", JSON.stringify(configuredCart));
  let authenticated = false;
  let orderCalls = 0;
  let cloverCalls = 0;
  globalThis.fetch = async (url, options = {}) => {
    const path = new URL(String(url), "https://cafe.test").pathname;
    if (path === "/api/v1/customer/auth/session") return response(authenticated ? 200 : 401, authenticated ? { user_id: "customer-1", role: "customer", csrf_token: "csrf" } : { detail: { code: "unauthenticated" } });
    if (path === "/api/v1/customer/auth/login") { authenticated = true; return response(200, { user_id: "customer-1", role: "customer", csrf_token: "csrf" }); }
    if (path === "/api/v1/customer/auth/register") return response(201, { message: "Check your email to verify your account." });
    if (path === "/api/v1/customer/profile") return response(200, { name: "Jessie Customer", email: "jessie@example.com", phone: "+15198816869", preferred_pickup_minutes: null, preferred_pickup_notes: "" });
    if (path === "/api/v1/catalog") return response(200, catalog);
    if (path === "/api/v1/scheduling/options") return response(200, { ordering_available: true, quick_pickup_options: [{ key: "asap", label: "ASAP", preference_minutes: null, requested_pickup_at: "2026-08-12T12:30:00Z" }], minimum_lead_time_minutes: 10, pickup_interval_minutes: 5, maximum_advance_days: 1, business_timezone: "UTC", custom_pickup_at: null, custom_pickup_error: null });
    if (path === "/api/v1/orders") {
      orderCalls += 1;
      assert.equal(authenticated, true);
      assert.equal(options.credentials, "include");
      return response(201, {
        public_token: "customer-order-token", status: "pending",
        requested_pickup_at: "2026-08-12T12:30:00Z", business_timezone: "UTC",
        customer: { name: "Jessie Customer", email: "jessie@example.com", phone: "+15198816869" },
        items: [{ product_slug: "coffee", product_name: "Coffee", variant_key: "large", variant_name: "Large", quantity: 3, line_subtotal_cents: 1350, modifiers: [{ group_name: "Sugar", option_name: "Sugar", quantity: 2 }] }],
        notes: "", subtotal_cents: 1350, tax_cents: 176, total_cents: 1526,
      });
    }
    if (path.includes("/api/v1/clover/orders/")) {
      cloverCalls += 1;
      assert.equal(authenticated, true);
      assert.equal(options.credentials, "include");
      return response(200, { checkout_session_id: "mock-session", checkout_url: "https://checkout.example.test/mock" });
    }
    throw new Error(`Unexpected request: ${path} ${options.method || "GET"}`);
  };
  const root = createRoot(document.getElementById("root"));
  try {
    await act(async () => root.render(React.createElement(MemoryRouter, { initialEntries: ["/menu"] }, React.createElement(CustomerAuthProvider, null, React.createElement(App)))));
    await waitForText(document.body, "Coffee");
    await click([...document.querySelectorAll("a")].find((link) => link.textContent.trim() === "Cart"), dom.window);
    await waitForText(document.body, "Your order");
    await click([...document.querySelectorAll("button")].find((button) => button.textContent.includes("Place order")), dom.window);
    await waitForText(document.body, "Sign in to place your order");
    assert.equal(orderCalls, 0); assert.equal(cloverCalls, 0);
    const authLink = [...document.querySelectorAll("a")].find((link) => link.textContent.trim() === (mode === "register" ? "Create Account" : "Sign In") && link.closest(".checkout-auth-required"));
    await click(authLink, dom.window);
    await waitForText(document.body, mode === "register" ? "Create Account" : "Welcome back");
    if (mode === "register") {
      assert.equal(localStorage.getItem("guesthouse-customer-auth-return"), "/cart");
      await click([...document.querySelectorAll("a")].find((link) => link.textContent.trim() === "Sign In"), dom.window);
      await waitForText(document.body, "Welcome back");
    }
    const loginInputs = document.querySelectorAll("form input");
    await input(loginInputs[0], "jessie@example.com", dom.window);
    await input(loginInputs[1], "correct horse battery staple", dom.window);
    await submit(document.querySelector("form"), dom.window);
    await waitForText(document.body, "Your order");
    const preserved = JSON.parse(localStorage.getItem("cafe-cart"));
    assert.deepEqual(preserved, configuredCart);
    assert.match(document.body.textContent, /Size: Large/);
    assert.match(document.body.textContent, /Sugar x2/);
    assert.match(document.body.textContent, /3 x \$4\.50/);
    assert.equal(orderCalls, 0); assert.equal(cloverCalls, 0);
    await click([...document.querySelectorAll("button")].find((button) => button.textContent.includes("Place order")), dom.window);
    for (let attempt = 0; attempt < 100 && cloverCalls === 0; attempt += 1) {
      await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
    }
    assert.equal(orderCalls, 1); assert.equal(cloverCalls, 1);
    assert.doesNotMatch(document.body.textContent, /A customer account is required/);
  } finally {
    await act(async () => root.unmount()); dom.window.close();
    globalThis.window = previous.window; globalThis.document = previous.document;
    globalThis.fetch = previous.fetch; globalThis.localStorage = previous.localStorage;
    globalThis.sessionStorage = previous.sessionStorage; globalThis.requestAnimationFrame = previous.requestAnimationFrame;
    Object.defineProperty(globalThis, "navigator", { configurable: true, value: previous.navigator });
  }
}

test("signed-out configured Cart signs in, preserves configuration, and submits with customer authority", { concurrency: false }, () => runContinuation("login"));
test("signed-out configured Cart continues through Create Account and submits with customer authority", { concurrency: false }, () => runContinuation("register"));
