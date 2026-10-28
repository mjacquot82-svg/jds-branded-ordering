import assert from "node:assert/strict";
import test from "node:test";

import {
  PaymentCheckoutError,
  createCheckout,
  confirmPayment,
} from "../../src/services/paymentService.js";

test("createCheckout uses the provider-neutral payments endpoint", async () => {
  const checkout = await createCheckout("token/with spaces", {
    apiBaseUrl: "https://api.example.test",
    fetchImpl: async (url, init) => {
      assert.equal(
        url,
        "https://api.example.test/api/v1/payments/orders/token%2Fwith%20spaces/checkout",
      );
      assert.equal(init.method, "POST");
      assert.equal(init.credentials, "include");
      return {
        ok: true,
        json: async () => ({
          provider: "clover",
          checkout_url: "https://checkout.example.test/session",
          checkout_session_id: "session-id",
        }),
      };
    },
  });
  assert.equal(checkout.checkout_session_id, "session-id");
  assert.equal(checkout.provider, "clover");
});

test("createCheckout surfaces provider-not-configured fail-closed errors", async () => {
  await assert.rejects(
    () =>
      createCheckout("saved-order", {
        fetchImpl: async () => ({
          ok: false,
          status: 503,
          json: async () => ({
            detail: {
              code: "payment_provider_not_configured",
              message: "No payment provider is configured for this business.",
            },
          }),
        }),
      }),
    (error) => {
      assert.ok(error instanceof PaymentCheckoutError);
      assert.equal(error.code, "payment_provider_not_configured");
      return true;
    },
  );
});

test("confirmPayment never invents an electronically paid state", async () => {
  const result = await confirmPayment({ status: "pending", payment_status: "unpaid" });
  assert.equal(result.paid, false);
  assert.equal(result.paymentId, null);
});
