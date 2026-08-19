import assert from "node:assert/strict";
import test from "node:test";

import {
  archiveOwnerProduct,
  clearOwnerCatalogCache,
  createOwnerModifierGroup,
  createOwnerModifierOption,
  fetchOwnerCatalog,
  fetchOwnerCatalogCached,
  saveOwnerCustomization,
  updateOwnerProductAvailability,
  updateOwnerModifierGroup,
  updateOwnerModifierOption,
  updateLunchSpecial,
  updateOwnerProduct,
} from "../../src/services/ownerCatalogApi.js";

function jsonResponse(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() { return payload; },
  };
}

test("owner catalog reads through the credentialed production API", async () => {
  let request;
  const payload = { categories: [], modifier_groups: [], products: [] };
  const result = await fetchOwnerCatalog({
    apiBaseUrl: "https://api.example.test/",
    fetchImpl: async (...args) => {
      request = args;
      return jsonResponse(200, payload);
    },
  });
  assert.deepEqual(result, payload);
  assert.equal(request[0], "https://api.example.test/api/v1/owner/catalog");
  assert.equal(request[1].credentials, "include");
});

test("Lunch Special writes use a narrow CSRF-protected payload", async () => {
  const calls = [];
  const fetchImpl = async (...args) => { calls.push(args); return jsonResponse(200, null); };
  await updateLunchSpecial(42, "csrf", { fetchImpl });
  await updateLunchSpecial(null, "csrf", { fetchImpl });
  assert.equal(calls[0][0], "/api/v1/owner/catalog/lunch-special");
  assert.equal(calls[0][1].method, "PUT");
  assert.equal(calls[0][1].headers["X-CSRF-Token"], "csrf");
  assert.deepEqual(JSON.parse(calls[0][1].body), { product_id: 42 });
  assert.deepEqual(JSON.parse(calls[1][1].body), { product_id: null });
});

test("owner catalog reuses an in-flight and recent read without hiding forced refreshes", async () => {
  clearOwnerCatalogCache();
  let calls = 0;
  const fetchImpl = async () => {
    calls += 1;
    return jsonResponse(200, { categories: [], modifier_groups: [], products: [] });
  };

  await Promise.all([
    fetchOwnerCatalogCached({ fetchImpl }),
    fetchOwnerCatalogCached({ fetchImpl }),
  ]);
  await fetchOwnerCatalogCached({ fetchImpl });
  assert.equal(calls, 1);

  await fetchOwnerCatalogCached({ fetchImpl, force: true });
  assert.equal(calls, 2);
  clearOwnerCatalogCache();
});

test("owner product writes use session CSRF and archive instead of hard delete", async () => {
  const calls = [];
  const fetchImpl = async (...args) => {
    calls.push(args);
    return args[1].method === "DELETE"
      ? { ok: true, status: 204 }
      : jsonResponse(200, { id: "42" });
  };
  await updateOwnerProduct("42", { name: "Generic product" }, "csrf", { fetchImpl });
  await archiveOwnerProduct("42", "csrf", { fetchImpl });

  assert.equal(calls[0][0], "/api/v1/owner/catalog/products/42");
  assert.equal(calls[0][1].method, "PUT");
  assert.equal(calls[0][1].headers["X-CSRF-Token"], "csrf");
  assert.equal(calls[1][1].method, "DELETE");
  assert.equal(calls[1][1].credentials, "include");
});

test("owner availability writes use the narrow CSRF-protected endpoint", async () => {
  let request;
  await updateOwnerProductAvailability("42", false, "csrf", {
    fetchImpl: async (...args) => {
      request = args;
      return jsonResponse(200, { id: "42", available: false });
    },
  });

  assert.equal(request[0], "/api/v1/owner/catalog/products/42/availability");
  assert.equal(request[1].method, "PATCH");
  assert.equal(request[1].credentials, "include");
  assert.equal(request[1].headers["X-CSRF-Token"], "csrf");
  assert.deepEqual(JSON.parse(request[1].body), { available: false });
});

test("modifier group and option writes use real IDs and CSRF-protected endpoints", async () => {
  const calls = [];
  const fetchImpl = async (...args) => { calls.push(args); return jsonResponse(200, { id: "9" }); };
  const group = { name: "Test group", selection_type: "single" };
  const option = { name: "Test option", price_adjustment_cents: 75 };
  await createOwnerModifierGroup(group, "csrf", { fetchImpl });
  await updateOwnerModifierGroup("42", group, "csrf", { fetchImpl });
  await createOwnerModifierOption("42", option, "csrf", { fetchImpl });
  await updateOwnerModifierOption("42", "9", option, "csrf", { fetchImpl });
  assert.deepEqual(calls.map(([url, request]) => [url, request.method]), [
    ["/api/v1/owner/catalog/modifier-groups", "POST"],
    ["/api/v1/owner/catalog/modifier-groups/42", "PUT"],
    ["/api/v1/owner/catalog/modifier-groups/42/options", "POST"],
    ["/api/v1/owner/catalog/modifier-groups/42/options/9", "PUT"],
  ]);
  assert.ok(calls.every(([, request]) => request.headers["X-CSRF-Token"] === "csrf"));
  assert.equal(JSON.parse(calls[3][1].body).price_adjustment_cents, 75);
});

test("one customization save creates its group then all drafted choices", async () => {
  const calls = [];
  let optionId = 0;
  const fetchImpl = async (url, request) => {
    calls.push([url, request]);
    if (url.endsWith("/modifier-groups")) return jsonResponse(201, { id: "42", key: "milk" });
    optionId += 1;
    return jsonResponse(201, { id: String(optionId), name: JSON.parse(request.body).name });
  };
  const result = await saveOwnerCustomization({
    group: { name: "Milk", selection_type: "single", required: false, min_selections: 0, max_selections: 1 },
    choices: [
      { clientId: "regular", payload: { name: "Regular milk", price_adjustment_cents: 0, active: true, sort_order: 0 } },
      { clientId: "oat", payload: { name: "Oat milk", price_adjustment_cents: 75, active: true, sort_order: 1 } },
    ],
  }, "csrf", { fetchImpl });
  assert.deepEqual(calls.map(([url, request]) => [url, request.method]), [
    ["/api/v1/owner/catalog/modifier-groups", "POST"],
    ["/api/v1/owner/catalog/modifier-groups/42/options", "POST"],
    ["/api/v1/owner/catalog/modifier-groups/42/options", "POST"],
  ]);
  assert.deepEqual(result.choices.map((item) => [item.clientId, item.response.id]), [["regular", "1"], ["oat", "2"]]);
  assert.ok(calls.every(([, request]) => request.headers["X-CSRF-Token"] === "csrf"));
});

test("partial customization failure exposes saved IDs so retry cannot duplicate records", async () => {
  let call = 0;
  const fetchImpl = async (url) => {
    call += 1;
    if (call === 1) return jsonResponse(201, { id: "42", key: "milk", name: "Milk" });
    if (call === 2) return jsonResponse(201, { id: "7", name: "Regular milk" });
    return jsonResponse(503, { detail: "Temporary catalog failure." });
  };
  await assert.rejects(
    saveOwnerCustomization({
      group: { name: "Milk" },
      choices: [
        { clientId: "regular", payload: { name: "Regular milk" } },
        { clientId: "oat", payload: { name: "Oat milk" } },
      ],
    }, "csrf", { fetchImpl }),
    (error) => {
      assert.match(error.message, /Milk was saved, but not every choice was saved/);
      assert.equal(error.partialCustomization.group.id, "42");
      assert.deepEqual(error.partialCustomization.choices.map((item) => [item.clientId, item.response.id]), [["regular", "7"]]);
      return true;
    },
  );
});
