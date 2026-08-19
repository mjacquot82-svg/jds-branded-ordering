import assert from "node:assert/strict";
import test from "node:test";

import {
  CloverCheckoutError,
  CloverConnectionError,
  createCloverCheckout,
  fetchCloverConnection,
  getCloverConnectUrl,
} from "../../src/services/cloverService.js";

test("Clover connection uses the authenticated Owner session", async () => {
  let request;
  const connection = await fetchCloverConnection({
    apiBaseUrl: "https://api.example.test/",
    fetchImpl: async (...args) => {
      request = args;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          configured: true,
          connected: true,
          environment: "production",
          merchant_id: "merchant-id",
        }),
      };
    },
  });

  assert.equal(request[1].credentials, "include");
  assert.equal(connection.connected, true);
  assert.equal(connection.merchant_id, "merchant-id");
});

test("Clover connection preserves authentication and backend errors", async () => {
  await assert.rejects(
    fetchCloverConnection({
      fetchImpl: async () => ({
        ok: false,
        status: 401,
        json: async () => ({
          detail: { code: "unauthenticated", message: "Authentication is required." },
        }),
      }),
    }),
    (error) => {
      assert.ok(error instanceof CloverConnectionError);
      assert.equal(error.code, "unauthenticated");
      assert.equal(error.status, 401);
      return true;
    },
  );
});

test("Clover connection distinguishes a network failure", async () => {
  await assert.rejects(
    fetchCloverConnection({
      fetchImpl: async () => { throw new TypeError("offline"); },
    }),
    (error) => {
      assert.ok(error instanceof CloverConnectionError);
      assert.equal(error.code, "network_error");
      assert.equal(error.status, undefined);
      return true;
    },
  );
});

test("createCloverCheckout requests the server-owned checkout endpoint", async () => {
  let request;
  const checkout = await createCloverCheckout("token/with spaces", {
    apiBaseUrl: "https://api.example.test/",
    fetchImpl: async (...args) => {
      request = args;
      return {
        ok: true,
        json: async () => ({
          checkout_url: "https://checkout.clover.test/session",
          checkout_session_id: "session-id",
        }),
      };
    },
  });

  assert.equal(
    request[0],
    "https://api.example.test/api/v1/clover/orders/token%2Fwith%20spaces/checkout"
  );
  assert.equal(request[1].method, "POST");
  assert.equal(request[1].credentials, "include");
  assert.equal(checkout.checkout_session_id, "session-id");
});

test("checkout surfaces the backend message when an order was already saved", async () => {
  await assert.rejects(
    createCloverCheckout("saved-order", {
      fetchImpl: async () => ({
        ok: false,
        status: 502,
        json: async () => ({
          detail: {
            code: "clover_rejected_request",
            message: "Your order was saved, but secure payment could not be started. Please try payment again.",
          },
        }),
      }),
    }),
    (error) => {
      assert.ok(error instanceof CloverCheckoutError);
      assert.equal(error.code, "clover_rejected_request");
      assert.equal(error.status, 502);
      assert.match(error.message, /order was saved/);
      assert.doesNotMatch(error.message, /check your connection/i);
      return true;
    },
  );
});

test("checkout mentions the customer connection only for a real fetch failure", async () => {
  await assert.rejects(
    createCloverCheckout("saved-order", {
      fetchImpl: async () => { throw new TypeError("offline"); },
    }),
    (error) => {
      assert.ok(error instanceof CloverCheckoutError);
      assert.equal(error.code, "network_error");
      assert.match(error.message, /check your connection/i);
      assert.match(error.message, /order was saved/i);
      return true;
    },
  );
});

test("getCloverConnectUrl supports a separately hosted API", () => {
  assert.equal(
    getCloverConnectUrl("https://api.example.test/"),
    "https://api.example.test/api/v1/clover/oauth/start"
  );
});
