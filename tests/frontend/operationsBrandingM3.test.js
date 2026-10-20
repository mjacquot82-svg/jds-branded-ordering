import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { JSDOM } from "jsdom";

import { applyOperationsBranding, applyStorefrontBranding, isOperationsPath, operationsTitle } from "../../src/tenant/operationsBranding.js";

const indexHtml = await readFile(new URL("../../index.html", import.meta.url), "utf8");
const storefront = { tenant: { id: "tenant-1" }, designVersion: 3, business: { displayName: "The Guest House" }, design: { template: "cozy", colors: { primary: "#123456" } } };

test("operations routes are recognised; customer storefront routes are not", () => {
  for (const path of ["/build", "/setup/brand", "/admin/platform", "/owner/login", "/staff", "/go-live", "/activate"]) assert.equal(isOperationsPath(path), true, path);
  for (const path of ["/", "/menu", "/checkout", "/account", "/builder", "/administer"]) assert.equal(isOperationsPath(path), false, path);
  assert.equal(operationsTitle("/build"), "Build your store · JDS Branded Ordering");
  assert.equal(operationsTitle("/setup/catalog"), "Set up your store · JDS Branded Ordering");
  assert.equal(operationsTitle("/admin/platform"), "Owner tools · JDS Branded Ordering");
});

test("operations branding replaces café title and icons with neutral JDS identity", () => {
  const { window } = new JSDOM(indexHtml);
  const doc = window.document;
  applyStorefrontBranding(doc, storefront);
  assert.equal(doc.title, "The Guest House · Order online");
  applyOperationsBranding(doc, "/setup/brand");
  assert.equal(doc.title, "Set up your store · JDS Branded Ordering");
  assert.doesNotMatch(doc.title, /Guest House|Ladel/);
  for (const icon of doc.querySelectorAll('link[rel="icon"],link[rel="shortcut icon"],link[rel="apple-touch-icon"]')) assert.equal(icon.getAttribute("href"), "/jds-operations-icon.svg");
  assert.equal(doc.documentElement.dataset.tenantTemplate, undefined);
  assert.equal(doc.documentElement.style.getPropertyValue("--tenant-primary"), "");
});

test("storefront branding is unchanged for customer routes", () => {
  const { window } = new JSDOM(indexHtml);
  const doc = window.document;
  applyStorefrontBranding(doc, storefront);
  assert.equal(doc.documentElement.dataset.tenantTemplate, "cozy");
  assert.equal(doc.documentElement.style.getPropertyValue("--tenant-primary"), "#123456");
  assert.equal(doc.querySelector('link[rel="apple-touch-icon"]').getAttribute("href"), "/api/v1/storefront/icon/192.png?tenant=tenant-1&v=3");
  assert.match(indexHtml, /<title>Ladel's Wellness Café<\/title>/); // storefront shell untouched
});

test("tenant provider and entrypoint apply operations branding before and after mount", async () => {
  const [provider, main] = await Promise.all([
    readFile(new URL("../../src/tenant/TenantContext.jsx", import.meta.url), "utf8"),
    readFile(new URL("../../src/main.jsx", import.meta.url), "utf8"),
  ]);
  assert.match(provider, /if \(isOperationsPath\(location\.pathname\)\) applyOperationsBranding\(document, location\.pathname\);\s*else if \(state\.status === "ready"\) applyStorefrontBranding\(document, state\.value\);/);
  assert.match(main, /if \(isOperationsPath\(location\.pathname\)\) applyOperationsBranding\(document, location\.pathname\);/);
});
