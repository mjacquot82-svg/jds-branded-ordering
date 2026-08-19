import assert from "node:assert/strict";
import test from "node:test";

import { fetchCustomerProfile, fetchCustomerQuickOrder, updateCustomerProfile } from "../../src/services/customerAccountApi.js";

test("customer profile hydration bypasses stale browser caches", async () => {
  let request;
  const profile = {
    email: "customer@example.com",
    name: "Customer Name",
    phone: "+15198816869",
  };

  const result = await fetchCustomerProfile({
    fetchImpl: async (...args) => {
      request = args;
      return { json: async () => profile, ok: true, status: 200 };
    },
  });

  assert.equal(request[0], "/api/v1/customer/profile");
  assert.equal(request[1].cache, "no-store");
  assert.equal(request[1].credentials, "include");
  assert.deepEqual(result, profile);
});

test("customer profile updates send only writable profile fields", async () => {
  let request;
  const writableProfile = {
    name: "Customer Name",
    phone: "+15198816869",
    preferred_pickup_minutes: 20,
    preferred_pickup_notes: "Side counter",
  };

  await updateCustomerProfile(writableProfile, "csrf-token", {
    fetchImpl: async (...args) => {
      request = args;
      return { json: async () => ({ ...writableProfile, email: "customer@example.com" }), ok: true, status: 200 };
    },
  });

  assert.equal(request[0], "/api/v1/customer/profile");
  assert.equal(request[1].method, "PUT");
  assert.equal(request[1].headers["X-CSRF-Token"], "csrf-token");
  assert.deepEqual(JSON.parse(request[1].body), writableProfile);
  assert.equal("email" in JSON.parse(request[1].body), false);
});

test("Quick Order personalization is a no-store customer read", async () => {
  let request;
  const result = await fetchCustomerQuickOrder({
    fetchImpl: async (...args) => {
      request = args;
      return { json: async () => ({ product_ids: ["4", "2"] }), ok: true, status: 200 };
    },
  });

  assert.deepEqual(result, { product_ids: ["4", "2"] });
  assert.equal(request[0], "/api/v1/customer/quick-order");
  assert.equal(request[1].cache, "no-store");
  assert.equal(request[1].credentials, "include");
});
