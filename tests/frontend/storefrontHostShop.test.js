import assert from "node:assert/strict";
import { after, test } from "node:test";

import { JSDOM } from "jsdom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// TenantContext.jsx is JSX, so load it through Vite the way the other runtime tests do.
const vite = await createServer({ appType: "custom", server: { hmr: false, middlewareMode: true } });
const { TenantProvider, shopSlugFromHostname, storefrontBaseDomain, storefrontBootstrapParams } =
  await vite.ssrLoadModule("/src/tenant/TenantContext.jsx");
after(() => vite.close());

const base = "order.jdsstudio.ca";
const response = (status, payload) => ({ json: async () => payload, ok: status >= 200 && status < 300, status });

test("shopSlugFromHostname reads the single label under the storefront base domain", () => {
  assert.equal(shopSlugFromHostname("maple.order.jdsstudio.ca", base), "maple");
  assert.equal(shopSlugFromHostname("zz-test-cafe.order.jdsstudio.ca", base), "zz-test-cafe");
  assert.equal(shopSlugFromHostname("MAPLE.Order.JDSStudio.CA", base), "maple");
  assert.equal(shopSlugFromHostname("maple.order.jdsstudio.ca.", base), "maple");
  assert.equal(shopSlugFromHostname("maple.order.jdsstudio.ca:443", base), "maple");
  assert.equal(shopSlugFromHostname("https://maple.order.jdsstudio.ca/menu", base), "maple");
});

test("shopSlugFromHostname ignores everything that is not exactly one shop label", () => {
  assert.equal(shopSlugFromHostname("a.b.order.jdsstudio.ca", base), null);
  assert.equal(shopSlugFromHostname("order.jdsstudio.ca", base), null);
  assert.equal(shopSlugFromHostname("order.jdsstudio.ca.", base), null);
  assert.equal(shopSlugFromHostname("www.order.jdsstudio.ca", base), null);
  assert.equal(shopSlugFromHostname(".order.jdsstudio.ca", base), null);
  assert.equal(shopSlugFromHostname("jds-beta-web.canner.app", base), null);
  assert.equal(shopSlugFromHostname("localhost", base), null);
  assert.equal(shopSlugFromHostname("localhost:5173", base), null);
  assert.equal(shopSlugFromHostname("127.0.0.1:8000", base), null);
  assert.equal(shopSlugFromHostname("", base), null);
  assert.equal(shopSlugFromHostname(null, base), null);
  // A label that is not a valid shop slug (shape, or the API's 3-63 length) is not a shop address either.
  assert.equal(shopSlugFromHostname("not_a_slug.order.jdsstudio.ca", base), null);
  assert.equal(shopSlugFromHostname("ab.order.jdsstudio.ca", base), null);
  assert.equal(shopSlugFromHostname(`${"a".repeat(64)}.order.jdsstudio.ca`, base), null);
  assert.equal(shopSlugFromHostname(`${"a".repeat(63)}.order.jdsstudio.ca`, base).length, 63);
});

test("the base domain comes from VITE_STOREFRONT_BASE_DOMAIN, defaulting to order.jdsstudio.ca", () => {
  assert.equal(storefrontBaseDomain({ VITE_STOREFRONT_BASE_DOMAIN: "shops.example.test" }), "shops.example.test");
  assert.equal(storefrontBaseDomain({ VITE_STOREFRONT_BASE_DOMAIN: " .Shops.Example.Test. " }), "shops.example.test");
  assert.equal(storefrontBaseDomain({}), "order.jdsstudio.ca");
  assert.equal(storefrontBaseDomain({ VITE_STOREFRONT_BASE_DOMAIN: "" }), "order.jdsstudio.ca");
  assert.equal(shopSlugFromHostname("maple.shops.example.test", "shops.example.test"), "maple");
});

test("bootstrap shop precedence is review_tenant, then shop, then the hosted address", () => {
  const hosted = "maple.order.jdsstudio.ca";
  assert.equal(storefrontBootstrapParams(hosted, "", base).toString(), "shop=maple");
  assert.equal(storefrontBootstrapParams(hosted, "?shop=other", base).toString(), "shop=other");
  assert.equal(storefrontBootstrapParams(hosted, "?review_tenant=the-guest-house", base).toString(), "review_tenant=the-guest-house");
  assert.equal(
    storefrontBootstrapParams(hosted, "?review_tenant=the-guest-house&shop=other", base).toString(),
    "review_tenant=the-guest-house",
  );
  // The Canner app host and localhost carry no shop of their own, so nothing is added.
  assert.equal(storefrontBootstrapParams("jds-beta-web.canner.app", "", base).toString(), "");
  assert.equal(storefrontBootstrapParams("localhost:5173", "?shop=maple", base).toString(), "shop=maple");
});

async function renderTenant({ url, status = 200, payload = {} }) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url });
  const previous = { document: globalThis.document, fetch: globalThis.fetch, location: globalThis.location, window: globalThis.window };
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.location = dom.window.location;
  const requests = [];
  globalThis.fetch = async (input) => { requests.push(String(input)); return status === 200 ? response(200, payload) : response(status, {}); };
  const container = document.getElementById("root");
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(MemoryRouter, { initialEntries: [new URL(url).pathname + new URL(url).search] }, React.createElement(TenantProvider, null, React.createElement("p", null, "storefront")))));
  for (let attempt = 0; attempt < 40 && container.querySelector(".tenant-gate"); attempt += 1) {
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
  }
  return {
    container,
    requests,
    async cleanup() {
      await act(async () => root.unmount());
      dom.window.close();
      globalThis.window = previous.window;
      globalThis.document = previous.document;
      globalThis.fetch = previous.fetch;
      if (previous.location === undefined) delete globalThis.location; else globalThis.location = previous.location;
    },
  };
}

const storefront = { tenant: { id: "t-1", slug: "maple" }, business: { displayName: "Maple Café" }, design: { displayName: "Maple Café" } };

test("a shop subdomain bootstraps that shop without a ?shop= link", { concurrency: false }, async () => {
  const app = await renderTenant({ url: "https://maple.order.jdsstudio.ca/menu", payload: storefront });
  try {
    assert.deepEqual(app.requests, ["/api/v1/storefront/bootstrap?shop=maple"]);
    assert.match(app.container.textContent, /storefront/);
  } finally {
    await app.cleanup();
  }
});

test("the Canner app host and localhost bootstrap exactly as before", { concurrency: false }, async () => {
  const canner = await renderTenant({ url: "https://jds-beta-web.canner.app/", payload: storefront });
  try {
    assert.deepEqual(canner.requests, ["/api/v1/storefront/bootstrap"]);
  } finally {
    await canner.cleanup();
  }
  const local = await renderTenant({ url: "http://localhost:5173/?shop=maple", payload: storefront });
  try {
    assert.deepEqual(local.requests, ["/api/v1/storefront/bootstrap?shop=maple"]);
  } finally {
    await local.cleanup();
  }
});

test("a subdomain shop that is not live yet still shows Opening soon", { concurrency: false }, async () => {
  const app = await renderTenant({ url: "https://zz-test-cafe.order.jdsstudio.ca/", status: 404 });
  try {
    assert.deepEqual(app.requests, ["/api/v1/storefront/bootstrap?shop=zz-test-cafe"]);
    assert.match(app.container.textContent, /Opening soon/);
    assert.doesNotMatch(app.container.textContent, /Storefront unavailable/);
  } finally {
    await app.cleanup();
  }
});
