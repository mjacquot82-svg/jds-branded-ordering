import assert from "node:assert/strict";
import test from "node:test";

import {
  createPendingOrder,
  fetchPendingOrder,
  OrderApiError,
} from "../../src/services/orderApi.js";

function pendingOrder() {
  return {
    public_token: "public-token",
    status: "pending",
    customer: { name: "Guest", email: "guest@example.com", phone: "5551234567" },
    items: [],
  };
}

test("createPendingOrder sends the exact order request contract", async () => {
  const calls = [];
  const payload = {
    idempotency_key: "request-key",
    customer: {
      name: "Guest",
      email: "guest@example.com",
      phone: "5551234567",
    },
    requested_pickup_at: "2026-07-28T12:30:00.000Z",
    notes: null,
    lines: [],
  };

  const order = await createPendingOrder(payload, {
    fetchImpl: async (...args) => {
      calls.push(args);
      return {
        ok: true,
        status: 201,
        json: async () => pendingOrder(),
      };
    },
  });

  assert.equal(order.public_token, "public-token");
  assert.equal(calls[0][0], "/api/v1/orders");
  assert.deepEqual(calls[0][1], {
    body: JSON.stringify(payload),
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    method: "POST",
    signal: undefined,
  });
});

test("fetchPendingOrder encodes the public token and supports abort", async () => {
  const signal = AbortSignal.abort();
  let request;

  await fetchPendingOrder("token/with spaces", {
    apiBaseUrl: "https://api.example.test/",
    fetchImpl: async (...args) => {
      request = args;
      return {
        ok: true,
        status: 200,
        json: async () => pendingOrder(),
      };
    },
    signal,
  });

  assert.equal(
    request[0],
    "https://api.example.test/api/v1/orders/token%2Fwith%20spaces"
  );
  assert.equal(request[1].signal, signal);
  assert.equal(request[1].credentials, "include");
});

test("order API errors preserve safe status and domain error codes", async () => {
  await assert.rejects(
    createPendingOrder({}, {
      fetchImpl: async () => ({
        ok: false,
        status: 409,
        json: async () => ({
          detail: {
            code: "idempotency_conflict",
            message: "Idempotency key was already used.",
          },
        }),
      }),
    }),
    (error) => {
      assert.ok(error instanceof OrderApiError);
      assert.equal(error.status, 409);
      assert.equal(error.code, "idempotency_conflict");
      assert.equal(error.message, "Idempotency key was already used.");
      return true;
    }
  );
});

test("order API reports network, invalid JSON, and malformed responses", async (context) => {
  await context.test("network failure", async () => {
    await assert.rejects(
      fetchPendingOrder("token", {
        fetchImpl: async () => {
          throw new TypeError("network detail");
        },
      }),
      (error) => {
        assert.ok(error instanceof OrderApiError);
        assert.equal(error.message, "Unable to reach the order service.");
        return true;
      }
    );
  });

  await context.test("invalid JSON", async () => {
    await assert.rejects(
      fetchPendingOrder("token", {
        fetchImpl: async () => ({
          ok: true,
          status: 200,
          json: async () => {
            throw new SyntaxError("invalid");
          },
        }),
      }),
      /invalid response/
    );
  });

  await context.test("malformed success", async () => {
    await assert.rejects(
      fetchPendingOrder("token", {
        fetchImpl: async () => ({
          ok: true,
          status: 200,
          json: async () => ({ status: "pending" }),
        }),
      }),
      /invalid shape/
    );
  });
});
