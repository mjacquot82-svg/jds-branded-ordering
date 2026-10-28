import assert from "node:assert/strict";
import { after, test } from "node:test";

import { JSDOM } from "jsdom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const vite = await createServer({ appType: "custom", server: { hmr: false, middlewareMode: true } });
const [{ default: App }, { CustomerAuthProvider }, { default: AppErrorBoundary }, { clearOwnerCatalogCache }] = await Promise.all([
  vite.ssrLoadModule("/src/App.jsx"),
  vite.ssrLoadModule("/src/auth/CustomerAuthContext.jsx"),
  vite.ssrLoadModule("/src/components/AppErrorBoundary.jsx"),
  vite.ssrLoadModule("/src/services/ownerCatalogApi.js"),
]);
after(() => vite.close());

const response = (payload, status = 200) => ({ json: async () => payload, ok: status >= 200 && status < 300, status });
const owner = {
  authenticated: true, app_launched: false, csrf_token: "csrf", display_name: "Owner",
  email: "owner@local.jds.test", organization_id: "org-1", role: "owner",
  permissions: ["catalog.read", "catalog.write", "catalog.publish", "availability.manage", "modifiers.manage", "lunch_special.manage"],
  onboarding_current_step: "catalog",
};

async function renderCatalog(catalog, expected) {
  clearOwnerCatalogCache();
  const dom = new JSDOM("<!doctype html><html><body><div id=\"root\"></div></body></html>", { url: "https://review.test/setup/catalog" });
  const previous = { document: globalThis.document, fetch: globalThis.fetch, navigator: globalThis.navigator, window: globalThis.window };
  globalThis.window = dom.window; globalThis.document = dom.window.document;
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
  dom.window.HTMLDialogElement.prototype.showModal = function showModal() { this.open = true; };
  dom.window.HTMLDialogElement.prototype.close = function close() { this.open = false; };
  globalThis.fetch = async (url) => {
    const path = new URL(String(url), "https://review.test").pathname;
    if (path === "/api/v1/customer/auth/session") return response({}, 401);
    if (path === "/api/v1/owner/auth/session") return response(owner);
    if (path === "/api/v1/owner/auth/organizations") return response([{ membership_id: "membership-1", organization_id: "org-1", organization_name: "New Merchant Demo — TEST" }]);
    if (path === "/api/v1/owner/platform-capabilities") return response({ capabilities: [] });
    if (path === "/api/v1/owner/onboarding") return response({ state: "in_progress", currentStep: "catalog", completedSteps: [], publicReady: false, revision: 1 });
    if (path === "/api/v1/owner/readiness") return response({ publicReady: false, checks: { catalog: Boolean(catalog.products.some((product) => product.published && product.available) && catalog.categories.some((category) => category.published)) } });
    if (path === "/api/v1/owner/catalog") return response(catalog);
    if (path === "/api/v1/owner/media") return response([]);
    throw new Error(`Unexpected request: ${path}`);
  };
  const root = createRoot(document.getElementById("root"));
  await act(async () => root.render(React.createElement(
    MemoryRouter,
    { initialEntries: ["/setup/catalog"] },
    React.createElement(CustomerAuthProvider, null, React.createElement(AppErrorBoundary, null, React.createElement(App))),
  )));
  for (let attempt = 0; attempt < 50 && !document.body.textContent.includes(expected) && !document.body.textContent.includes("Something went wrong"); attempt += 1) await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
  return { dom, root, async cleanup() { await act(async () => root.unmount()); dom.window.close(); globalThis.window = previous.window; globalThis.document = previous.document; globalThis.fetch = previous.fetch; Object.defineProperty(globalThis, "navigator", { configurable: true, value: previous.navigator }); } };
}

const category = { id: "1", slug: "coffee", name: "Coffee", note: "", published: true, sort_order: 0 };
const product = { id: "2", slug: "latte", name: "Latte", description: "", base_price_cents: 475, category_id: "1", image: "", available: true, featured: false, lunch_special: false, published: true, archived: false, sort_order: 0, variants: [], modifier_group_ids: [] };

for (const [name, catalog, expected] of [
  ["zero categories and zero products", { categories: [], modifier_groups: [], products: [] }, "Create your first category"],
  ["one category and zero products", { categories: [category], modifier_groups: [], products: [] }, "Now add your first product to Coffee"],
  ["a populated catalog", { categories: [category], modifier_groups: [], products: [product] }, "Latte"],
]) test(`Step 4 renders ${name} without reaching the error boundary`, { concurrency: false }, async () => {
  const app = await renderCatalog(catalog, expected);
  try { assert.match(document.body.textContent, new RegExp(expected)); assert.doesNotMatch(document.body.textContent, /Something went wrong/); }
  finally { await app.cleanup(); }
});
