import assert from "node:assert/strict";
import test from "node:test";

import { createCatalogResource } from "../../src/services/catalogResource.js";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

test("catalog resource publishes loading and ready states", async () => {
  const request = deferred();
  const catalog = { categories: [{ id: "coffee" }] };
  const resource = createCatalogResource({
    fetchCatalogImpl: () => request.promise,
    adaptCatalogImpl: () => catalog,
  });
  const states = [];
  const unsubscribe = resource.subscribe((state) => states.push(state.status));

  const load = resource.load();
  assert.equal(resource.getState().status, "loading");
  request.resolve({ version: "1", categories: [] });
  assert.equal((await load).status, "ready");
  assert.equal(resource.getState().catalog, catalog);
  assert.deepEqual(states, ["idle", "loading", "ready"]);

  unsubscribe();
});

test("catalog resource distinguishes a successful empty catalog", async () => {
  const catalog = { categories: [] };
  const resource = createCatalogResource({
    fetchCatalogImpl: async () => ({ version: "1", categories: [] }),
    adaptCatalogImpl: () => catalog,
  });

  const state = await resource.load();

  assert.deepEqual(state, {
    status: "empty",
    catalog,
    error: null,
  });
});

test("catalog resource publishes errors and supports retry", async () => {
  const failure = new Error("catalog unavailable");
  let attempts = 0;
  const resource = createCatalogResource({
    fetchCatalogImpl: async () => {
      attempts += 1;
      if (attempts === 1) throw failure;
      return { version: "1", categories: [] };
    },
    adaptCatalogImpl: () => ({ categories: [{ id: "coffee" }] }),
  });

  const failed = await resource.load();
  assert.equal(failed.status, "error");
  assert.equal(failed.catalog, null);
  assert.equal(failed.error, failure);

  const recovered = await resource.load();
  assert.equal(recovered.status, "ready");
  assert.equal(recovered.error, null);
});

test("catalog resource ignores completion from an obsolete request", async () => {
  const first = deferred();
  const second = deferred();
  let requestCount = 0;
  const resource = createCatalogResource({
    fetchCatalogImpl: () => {
      requestCount += 1;
      return requestCount === 1 ? first.promise : second.promise;
    },
    adaptCatalogImpl: (payload) => payload,
  });

  const firstLoad = resource.load();
  const secondLoad = resource.load();
  second.resolve({ categories: [{ id: "new" }] });
  await secondLoad;
  first.resolve({ categories: [{ id: "old" }] });
  await firstLoad;

  assert.deepEqual(resource.getState().catalog, {
    categories: [{ id: "new" }],
  });
});
