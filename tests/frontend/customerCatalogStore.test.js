import assert from "node:assert/strict";
import test from "node:test";

import { createCustomerCatalogResource } from "../../src/stores/customerCatalogStore.js";

test("customer catalog resource follows loading, ready, empty, and retry states", async () => {
  const requests = [];
  let attempt = 0;
  const resource = createCustomerCatalogResource({
    fetchCatalogImpl: async () => {
      attempt += 1;
      requests.push(attempt);
      if (attempt === 1) throw new Error("temporary failure");
      if (attempt === 2) return { version: "1", categories: [] };
      return { version: "1", categories: [{ id: "coffee" }] };
    },
    adaptCatalogImpl: (payload) => ({
      categories: payload.categories,
      products: [],
    }),
  });
  const states = [];
  resource.subscribe((state) => states.push(state.status));

  assert.equal((await resource.load()).status, "error");
  assert.equal((await resource.load()).status, "empty");
  assert.equal((await resource.load()).status, "ready");
  assert.deepEqual(requests, [1, 2, 3]);
  assert.deepEqual(states, [
    "idle",
    "loading",
    "error",
    "loading",
    "empty",
    "loading",
    "ready",
  ]);
});
