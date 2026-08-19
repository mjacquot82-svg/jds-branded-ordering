import assert from "node:assert/strict";
import test from "node:test";
import { readTenantLocalStorage, tenantBrowserKey, writeTenantLocalStorage } from "../../src/services/tenantBrowserState.js";

function memoryStorage() {
  const values = new Map();
  return { getItem: (key) => values.has(key) ? values.get(key) : null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
}

test("browser state keys include the normalized storefront hostname", () => {
  assert.equal(tenantBrowserKey("cafe-cart", "CAFE-A.JDSSTUDIO.CA"), "jds:cafe-a.jdsstudio.ca:cafe-cart");
  assert.notEqual(tenantBrowserKey("cafe-cart", "cafe-a.jdsstudio.ca"), tenantBrowserKey("cafe-cart", "cafe-b.jdsstudio.ca"));
});

test("cart state from one production storefront is invisible on another", () => {
  const storage = memoryStorage();
  const previous = globalThis.location;
  try {
    globalThis.location = { hostname: "cafe-a.jdsstudio.ca" };
    writeTenantLocalStorage("cafe-cart", "tenant-a", storage);
    globalThis.location = { hostname: "cafe-b.jdsstudio.ca" };
    assert.equal(readTenantLocalStorage("cafe-cart", storage), null);
    writeTenantLocalStorage("cafe-cart", "tenant-b", storage);
    globalThis.location = { hostname: "cafe-a.jdsstudio.ca" };
    assert.equal(readTenantLocalStorage("cafe-cart", storage), "tenant-a");
  } finally {
    if (previous === undefined) delete globalThis.location;
    else globalThis.location = previous;
  }
});
