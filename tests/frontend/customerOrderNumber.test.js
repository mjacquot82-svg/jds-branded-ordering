import assert from "node:assert/strict";
import { after, test } from "node:test";
import { JSDOM } from "jsdom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const vite = await createServer({ appType: "custom", server: { hmr: false, middlewareMode: true } });
const [{ default: ConfirmationPage }, { orderReference }] = await Promise.all([
  vite.ssrLoadModule("/src/pages/ConfirmationPage.jsx"),
  vite.ssrLoadModule("/src/services/orderReference.js"),
]);
after(() => vite.close());

// The order the API returns: a readable queue number plus the unchanged public token.
const order = {
  reference: "ZTC-000010",
  public_token: "SKB5OKIVabcdefghijklmnop",
  status: "pending",
  customer: { name: "Jessie Guest", email: "jessie@example.com", phone: "+15551234567" },
  notes: null,
  requested_pickup_at: "2026-08-12T12:30:00Z",
  business_timezone: "America/Toronto",
  currency: "CAD",
  subtotal_cents: 500,
  tax_cents: 9,
  total_cents: 509,
  expires_at: "2026-08-12T13:30:00Z",
  created_at: "2026-08-12T12:00:00Z",
  updated_at: "2026-08-12T12:00:00Z",
  items: [{ product_slug: "latte", product_name: "Test Latte", variant_key: null, variant_name: null, quantity: 1, line_subtotal_cents: 500, modifiers: [] }],
};

test("the confirmation page shows the same order number the shop's queue shows", async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: "https://zztestcafegrokqa.order.jdsstudio.ca/confirmation" });
  const previous = { window: globalThis.window, document: globalThis.document, navigator: globalThis.navigator };
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
  const root = createRoot(dom.window.document.querySelector("#root"));
  try {
    await act(async () => root.render(React.createElement(
      MemoryRouter,
      { initialEntries: [{ pathname: "/confirmation", search: `?order=${order.public_token}`, state: { order } }] },
      React.createElement(ConfirmationPage),
    )));
    const text = dom.window.document.body.textContent;
    assert.match(text, /Order ZTC-000010/, "the readable queue number is what the customer reads");
    // The public token is the unguessable URL key: it must never be printed for a customer.
    assert.doesNotMatch(text, /SKB5OKIV/);
    assert.doesNotMatch(text, /SKB5OKIVABCDEF/i);
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
    globalThis.window = previous.window;
    globalThis.document = previous.document;
    Object.defineProperty(globalThis, "navigator", { configurable: true, value: previous.navigator });
  }
});

test("orderReference reads the API field and never derives a number from the token", () => {
  assert.equal(orderReference({ reference: "ZTC-000010", public_token: "SKB5OKIVabcdef" }), "ZTC-000010");
  assert.equal(orderReference({ reference: "  MAP-000123  " }), "MAP-000123");
  // An older response without the field shows nothing rather than a token fragment.
  assert.equal(orderReference({ public_token: "SKB5OKIVabcdef" }), "");
  assert.equal(orderReference(null), "");
});
