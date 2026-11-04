import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { JSDOM } from "jsdom";

import { applyManifestLink, applyOperationsBranding, applyStorefrontBranding } from "../../src/tenant/operationsBranding.js";

const indexHtml = await readFile(new URL("../../index.html", import.meta.url), "utf8");
// The real index.html shell: a manifest link the static build cannot resolve, plus the icons.
const shell = '<!doctype html><html><head>'
  + '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png" />'
  + '<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />'
  + '<link rel="manifest" href="/api/v1/storefront/manifest.webmanifest" />'
  + '<meta name="theme-color" content="#4c3426" /></head><body></body></html>';
const storefront = { tenant: { id: "t-1", slug: "zztestcafegrokqa", canonicalHost: "zztestcafegrokqa.order.jdsstudio.ca" }, designVersion: 4, business: { displayName: "ZZ Test Cafe (Grok QA)" }, design: { template: "cozy", colors: { primary: "#1e66d0" } } };

test("a shop page points the browser at that shop's own manifest", () => {
  const { window } = new JSDOM(shell);
  applyStorefrontBranding(window.document, storefront);
  const manifests = window.document.querySelectorAll('link[rel="manifest"]');
  assert.equal(manifests.length, 1, "exactly one manifest link");
  const href = manifests[0].getAttribute("href");
  assert.equal(href, "/api/v1/storefront/manifest.webmanifest?shop=zztestcafegrokqa");
  // The link names this shop, so the response can only be this shop's data.
  assert.equal(new URL(href, "https://zztestcafegrokqa.order.jdsstudio.ca").searchParams.get("shop"), "zztestcafegrokqa");
});

test("the linked icon also names the shop so it resolves on the shop's own address", () => {
  const { window } = new JSDOM(shell);
  applyStorefrontBranding(window.document, storefront);
  const icon = window.document.querySelector('link[rel="apple-touch-icon"]');
  const params = new URL(icon.getAttribute("href"), "https://example.test").searchParams;
  assert.equal(params.get("shop"), "zztestcafegrokqa");
  assert.equal(params.get("tenant"), "t-1");
});

test("a page with no shop asks for no manifest, so no request can 404", () => {
  const { window } = new JSDOM(shell);
  applyOperationsBranding(window.document, "/admin");
  assert.equal(window.document.querySelectorAll('link[rel="manifest"]').length, 0);
});

test("a shop's page gets its manifest back after leaving an operations route", () => {
  const { window } = new JSDOM(shell);
  applyOperationsBranding(window.document, "/admin");
  applyStorefrontBranding(window.document, storefront);
  const manifests = window.document.querySelectorAll('link[rel="manifest"]');
  assert.equal(manifests.length, 1);
  assert.match(manifests[0].getAttribute("href"), /shop=zztestcafegrokqa$/);
});

test("applyManifestLink re-points one link instead of stacking shop links", () => {
  const { window } = new JSDOM(shell);
  applyManifestLink(window.document, "maple");
  applyManifestLink(window.document, "second-street");
  const hrefs = [...window.document.querySelectorAll('link[rel="manifest"]')].map((link) => link.getAttribute("href"));
  assert.deepEqual(hrefs, ["/api/v1/storefront/manifest.webmanifest?shop=second-street"]);
});

test("the served page no longer hard-codes a manifest that cannot know the shop", () => {
  assert.doesNotMatch(indexHtml, /rel="manifest"/);
});

test("a review storefront asks for its manifest the same way it was bootstrapped", () => {
  const { window } = new JSDOM(shell);
  applyStorefrontBranding(
    window.document,
    { ...storefront, tenant: { id: "t-2", slug: "the-guest-house" }, review: { staging: true, label: "STAGING" } },
    new URLSearchParams("review_tenant=second-street-cafe"),
  );
  const href = window.document.querySelector('link[rel="manifest"]').getAttribute("href");
  assert.equal(href, "/api/v1/storefront/manifest.webmanifest?review_tenant=second-street-cafe");
});
