import assert from "node:assert/strict";
import test from "node:test";

import {
  CatalogApiError,
  fetchCatalog,
} from "../../src/services/catalogApi.js";

test("fetchCatalog requests the same-origin versioned catalog", async () => {
  const calls = [];
  const payload = {
    version: "1",
    generated_at: "2026-07-27T00:00:00Z",
    pricing: { tax_name: "HST", tax_rate_millionths: 1_300_000 },
    categories: [],
  };

  const result = await fetchCatalog({
    fetchImpl: async (...args) => {
      calls.push(args);
      return {
        ok: true,
        status: 200,
        json: async () => payload,
      };
    },
  });

  assert.equal(result, payload);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "/api/v1/catalog");
  assert.deepEqual(calls[0][1], {
    headers: { Accept: "application/json" },
    method: "GET",
    signal: undefined,
  });
});

test("fetchCatalog supports an explicit API base URL and abort signal", async () => {
  const signal = AbortSignal.abort();
  let request;

  await fetchCatalog({
    apiBaseUrl: "https://api.example.test/",
    signal,
    fetchImpl: async (...args) => {
      request = args;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          version: "1",
          pricing: { tax_name: "HST", tax_rate_millionths: 1_300_000 },
          categories: [],
        }),
      };
    },
  });

  assert.equal(request[0], "https://api.example.test/api/v1/catalog");
  assert.equal(request[1].signal, signal);
});

test("fetchCatalog reports HTTP failures without exposing response content", async () => {
  await assert.rejects(
    fetchCatalog({
      fetchImpl: async () => ({ ok: false, status: 503 }),
    }),
    (error) => {
      assert.ok(error instanceof CatalogApiError);
      assert.equal(error.status, 503);
      assert.equal(error.message, "The catalog service returned an error.");
      return true;
    }
  );
});

test("fetchCatalog reports network and JSON failures", async (context) => {
  await context.test("network failure", async () => {
    const cause = new Error("internal network detail");
    await assert.rejects(
      fetchCatalog({
        fetchImpl: async () => {
          throw cause;
        },
      }),
      (error) => {
        assert.ok(error instanceof CatalogApiError);
        assert.equal(error.message, "Unable to reach the catalog service.");
        assert.equal(error.cause, cause);
        return true;
      }
    );
  });

  await context.test("invalid JSON", async () => {
    await assert.rejects(
      fetchCatalog({
        fetchImpl: async () => ({
          ok: true,
          status: 200,
          json: async () => {
            throw new SyntaxError("invalid");
          },
        }),
      }),
      (error) => {
        assert.ok(error instanceof CatalogApiError);
        assert.equal(error.message, "The catalog service returned invalid JSON.");
        return true;
      }
    );
  });
});

test("fetchCatalog rejects a malformed response envelope", async () => {
  await assert.rejects(
    fetchCatalog({
      fetchImpl: async () => ({
        ok: true,
        status: 200,
        json: async () => ({ categories: "not-an-array" }),
      }),
    }),
    (error) => {
      assert.ok(error instanceof CatalogApiError);
      assert.equal(error.message, "The catalog response has an invalid shape.");
      return true;
    }
  );
});
