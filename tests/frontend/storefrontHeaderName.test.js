import assert from "node:assert/strict";
import { after, test } from "node:test";
import { JSDOM } from "jsdom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { readFile } from "node:fs/promises";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const vite = await createServer({ appType: "custom", server: { hmr: false, middlewareMode: true } });
const [
  { default: HeaderBrandingIdentity },
  { default: LayoutPhonePreview, FocusedHeaderBrandingPreview },
  { getLayoutDefinition },
] = await Promise.all([
  vite.ssrLoadModule("/src/design/HeaderBrandingIdentity.jsx"),
  vite.ssrLoadModule("/src/design/LayoutPhonePreview.jsx"),
  vite.ssrLoadModule("/src/design/layoutDefinitions.js"),
]);
after(() => vite.close());

// The exact shape /api/v1/storefront/bootstrap returns for the test shop.
const bootstrap = {
  tenant: { id: "t-1", slug: "zztestcafegrokqa", canonicalHost: "zztestcafegrokqa.order.jdsstudio.ca" },
  business: { displayName: "ZZ Test Cafe (Grok QA)" },
  design: {
    template: "cozy",
    displayName: "ZZ Test Cafe (Grok QA)",
    tagline: "Specialty coffee, fresh pastries, warm welcome",
    colors: { primary: "#1e66d0", accent: "#c4784a", background: "#f6f1ea", surface: "#ffffff", text: "#2a2f28" },
    branding: { showLogo: true, showHero: true, headerMode: "tagline" },
    typography: "classic",
    buttonStyle: "rounded",
    imagePositions: { logo: { x: 50, y: 50, zoom: 1 }, hero: { x: 50, y: 50, zoom: 1 }, appIcon: { x: 50, y: 50, zoom: 1 } },
    sections: ["hero", "announcement", "categories", "quickOrder"],
  },
};
const layout = getLayoutDefinition("cozy");

async function render(element) {
  const dom = new JSDOM('<div id="root"></div>', { url: "https://zztestcafegrokqa.order.jdsstudio.ca/" });
  const previous = { window: globalThis.window, document: globalThis.document, navigator: globalThis.navigator };
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
  const root = createRoot(dom.window.document.querySelector("#root"));
  await act(async () => root.render(element));
  return {
    dom,
    root,
    async cleanup() {
      await act(async () => root.unmount());
      dom.window.close();
      globalThis.window = previous.window;
      globalThis.document = previous.document;
      Object.defineProperty(globalThis, "navigator", { configurable: true, value: previous.navigator });
    },
  };
}

test("the storefront header shows the shop name as its primary text", async () => {
  const { dom, cleanup } = await render(React.createElement(HeaderBrandingIdentity, { config: bootstrap.design, layout }));
  try {
    const name = dom.window.document.querySelector(".header-branding-identity .header-branding-name");
    assert.equal(name?.textContent, "ZZ Test Cafe (Grok QA)", "the shop name is the header's primary text");
    const identity = dom.window.document.querySelector(".header-branding-identity");
    assert.equal(identity.firstElementChild, name, "the name comes first, before any tagline");
  } finally {
    await cleanup();
  }
});

test("the tagline is a secondary line under the name and never replaces it", async () => {
  const { dom, cleanup } = await render(React.createElement(HeaderBrandingIdentity, { config: bootstrap.design, layout }));
  try {
    const tagline = dom.window.document.querySelector(".header-branding-tagline");
    assert.equal(tagline?.textContent, "Specialty coffee, fresh pastries, warm welcome");
    const identity = dom.window.document.querySelector(".header-branding-identity");
    assert.equal(identity.textContent, "ZZ Test Cafe (Grok QA)Specialty coffee, fresh pastries, warm welcome");
    // The regression was the tagline standing alone in the name slot.
    assert.notEqual(identity.querySelector("strong"), null);
    assert.notEqual(identity.querySelector("strong")?.textContent, tagline?.textContent);
  } finally {
    await cleanup();
  }
});

test("a shop with no tagline still shows its name", async () => {
  const config = { ...bootstrap.design, tagline: "" };
  const { dom, cleanup } = await render(React.createElement(HeaderBrandingIdentity, { config, layout }));
  try {
    assert.equal(dom.window.document.querySelector(".header-branding-name")?.textContent, "ZZ Test Cafe (Grok QA)");
    assert.equal(dom.window.document.querySelector(".header-branding-tagline"), null);
  } finally {
    await cleanup();
  }
});

test("a header logo still stands in for the name when the shop has one", async () => {
  const { dom, cleanup } = await render(React.createElement(LayoutPhonePreview, {
    config: { ...bootstrap.design, branding: { ...bootstrap.design.branding, headerMode: "logo" } },
    logoUrl: "/api/v1/storefront/media/42",
  }));
  try {
    const image = dom.window.document.querySelector('.header-branding-identity.mode-logo img');
    assert.equal(image?.getAttribute("src"), "/api/v1/storefront/media/42");
    assert.equal(dom.window.document.querySelector(".header-branding-name"), null);
  } finally {
    await cleanup();
  }
});

test("the phone preview and the design studio header show the same name first", async () => {
  const { dom, cleanup } = await render(React.createElement("div", null,
    React.createElement(LayoutPhonePreview, { config: bootstrap.design, designer: { activeSlot: "tagline" } }),
    React.createElement(FocusedHeaderBrandingPreview, { config: bootstrap.design, layout, designer: { activeSlot: "tagline" } }),
  ));
  try {
    const identities = [...dom.window.document.querySelectorAll(".header-branding-identity")];
    assert.ok(identities.length >= 2, "phone header and focused header preview both render");
    for (const identity of identities) {
      assert.equal(identity.firstElementChild?.className, "header-branding-name");
      assert.equal(identity.firstElementChild?.textContent, "ZZ Test Cafe (Grok QA)");
    }
  } finally {
    await cleanup();
  }
});

test("the storefront shell names the shop even when only the business profile carries it", async () => {
  const layoutSource = await readFile(new URL("../../src/layouts/AppLayout.jsx", import.meta.url), "utf8");
  // The design's name is used when present, and the business profile's name is the fallback.
  assert.match(layoutSource, /const headerConfig = \{ \.\.\.tenant\.value\?\.design, displayName: tenant\.value\?\.design\?\.displayName \|\| tenant\.value\?\.business\?\.displayName \|\| "" \}/);
  assert.match(layoutSource, /<HeaderBrandingIdentity config=\{headerConfig\}/);

  const nameOnly = { ...bootstrap.design, displayName: "" };
  const { dom, cleanup } = await render(React.createElement(HeaderBrandingIdentity, { config: { ...nameOnly, displayName: bootstrap.business.displayName }, layout }));
  try {
    assert.equal(dom.window.document.querySelector(".header-branding-name")?.textContent, "ZZ Test Cafe (Grok QA)");
  } finally {
    await cleanup();
  }
});
