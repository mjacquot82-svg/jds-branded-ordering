import assert from "node:assert/strict";
import test from "node:test";

import { fetchOwnerCustomers } from "../../src/services/ownerCustomersApi.js";

test("owner customer administration reads only the authenticated business endpoint", async () => {
  let request;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return new Response(JSON.stringify({ customers: [{ id: "customer-a" }] }), {
      headers: { "Content-Type": "application/json" }, status: 200,
    });
  };
  try {
    assert.deepEqual(await fetchOwnerCustomers("A&B"), [{ id: "customer-a" }]);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(request.url, "/api/v1/owner/customers?q=A%26B");
  assert.equal(request.options.credentials, "include");
  assert.equal(request.options.cache, "no-store");
  assert.doesNotMatch(request.url, /tenant|organization/);
});
