import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPendingOrderRequest,
  canonicalizeCheckoutContact,
  clearOrderSubmission,
  createSubmissionGate,
  getOrderErrorMessage,
  formatPickupTimeInput,
  isCheckoutContactComplete,
  prepareOrderSubmission,
  resolveVisibleCheckoutContact,
} from "../../src/services/checkoutOrder.js";
import { OrderApiError } from "../../src/services/orderApi.js";
import { CloverCheckoutError } from "../../src/services/cloverService.js";

function resolvedLine() {
  return {
    name: "Latte",
    productBackendId: "101",
    quantity: 2,
    options: [
      { backendId: "201", variantId: "201", name: "Large" },
      { backendId: "301", name: "Oat" },
      { backendId: "302", name: "Vanilla" },
    ],
  };
}

function createSessionStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.get(key) ?? null;
    },
    removeItem(key) {
      values.delete(key);
    },
    setItem(key, value) {
      values.set(key, value);
    },
  };
}

test("buildPendingOrderRequest maps cart snapshots without client prices", () => {
  const request = buildPendingOrderRequest({
    contact: {
      name: "  Jessie Guest ",
      email: " jessie@example.com ",
      phone: "(555) 123-4567",
    },
    idempotencyKey: "stable-request-key",
    lines: [resolvedLine()],
    notes: "  Extra hot ",
    requestedPickupAt: "2026-07-28T12:30:00.000Z",
  });

  assert.deepEqual(request, {
    idempotency_key: "stable-request-key",
    customer: {
      name: "Jessie Guest",
      email: "jessie@example.com",
      phone: "+15551234567",
    },
    requested_pickup_at: "2026-07-28T12:30:00.000Z",
    notes: "Extra hot",
    lines: [
      {
        product_id: 101,
        variant_id: 201,
        modifier_selections: [
          { modifier_option_id: 301, quantity: 1 },
          { modifier_option_id: 302, quantity: 1 },
        ],
        quantity: 2,
      },
    ],
  });
  assert.equal("price_cents" in request.lines[0], false);
});

test("profile defaults and formatted phones share one canonical checkout contact", () => {
  const visibleContact = {
    name: "Jessie Guest",
    email: "jessie@example.com",
    phone: "(519) 881-6869",
  };

  assert.equal(isCheckoutContactComplete(visibleContact), true);
  assert.deepEqual(canonicalizeCheckoutContact(visibleContact), {
    name: "Jessie Guest",
    email: "jessie@example.com",
    phone: "+15198816869",
  });
});

test("checkout contact requires an actual first and last name", () => {
  const contact = {
    name: "mjacquot82",
    email: "marc@example.com",
    phone: "(519) 881-6869",
  };

  assert.equal(isCheckoutContactComplete(contact), false);
  assert.equal(isCheckoutContactComplete({ ...contact, name: "Marc Jacquot" }), true);
});

test("resolved pickup times populate the native time control in the business timezone", () => {
  assert.equal(
    formatPickupTimeInput("2026-08-05T17:25:00.000Z", "America/Toronto"),
    "13:25"
  );
  assert.equal(formatPickupTimeInput(null, "America/Toronto"), "");
});

test("visible autofilled checkout values override stale React contact state", () => {
  assert.deepEqual(
    resolveVisibleCheckoutContact(
      { name: "", email: "", phone: "" },
      {
        name: "Jessie Guest",
        email: "jessie@example.com",
        phone: "(519) 881-6869",
      }
    ),
    {
      name: "Jessie Guest",
      email: "jessie@example.com",
      phone: "+15198816869",
    }
  );
});

test("buildPendingOrderRequest rejects missing opaque identifiers", () => {
  assert.throws(
    () =>
      buildPendingOrderRequest({
        contact: { name: "Guest", email: "guest@example.com", phone: "5551234" },
        idempotencyKey: "request-key",
        lines: [{ ...resolvedLine(), productBackendId: null }],
        notes: "",
        requestedPickupAt: "2026-07-28T12:30:00.000Z",
      }),
    /product is unavailable/
  );
});

test("getOrderErrorMessage translates stable API codes for customers", () => {
  assert.match(
    getOrderErrorMessage(
      new OrderApiError("internal", {
        code: "modifier_option_invalid",
        status: 422,
      })
    ),
    /customization has changed/
  );
  assert.equal(
    getOrderErrorMessage(
      new OrderApiError("Pickup time is outside business hours.", {
        code: "pickup_invalid",
        status: 422,
      })
    ),
    "Pickup time is outside business hours."
  );
  assert.doesNotMatch(
    getOrderErrorMessage(new TypeError("unexpected")),
    /connection/i,
  );
  assert.equal(
    getOrderErrorMessage(new CloverCheckoutError(
      "Your order was saved, but secure payment could not be started.",
      { code: "clover_rejected_request", status: 502 },
    )),
    "Your order was saved, but secure payment could not be started.",
  );
});

test("submission gate freezes rapid interaction until the request settles", () => {
  const gate = createSubmissionGate();
  const cart = [{ quantity: 1 }];
  const submittedSnapshot = structuredClone(cart);

  assert.equal(gate.begin(), true);
  assert.equal(gate.isInFlight(), true);
  assert.equal(gate.begin(), false);

  if (!gate.isInFlight()) {
    cart[0].quantity = 2;
  }
  assert.deepEqual(submittedSnapshot, [{ quantity: 1 }]);
  assert.deepEqual(cart, [{ quantity: 1 }]);

  gate.end();
  assert.equal(gate.isInFlight(), false);
});

test("ambiguous failure and remount reuse the persisted idempotency key", async () => {
  const storage = createSessionStorage();
  const payload = buildPendingOrderRequest({
    contact: {
      name: "Jessie Guest",
      email: "jessie@example.com",
      phone: "+15551234567",
    },
    idempotencyKey: "",
    lines: [resolvedLine()],
    notes: "Extra hot",
    requestedPickupAt: "2026-07-28T12:30:00.000Z",
  });

  const fingerprintPayload = {
    ...payload,
    requested_pickup_at: {
      business_date: "2026-07-28",
      custom_time: null,
      selection: "asap",
    },
  };
  const firstMountSubmission = await prepareOrderSubmission(
    payload,
    { fingerprintPayload, storage }
  );
  const remountedSubmission = await prepareOrderSubmission(
    {
      ...structuredClone(payload),
      requested_pickup_at: "2026-07-28T12:35:00.000Z",
    },
    { fingerprintPayload: structuredClone(fingerprintPayload), storage }
  );

  assert.equal(
    remountedSubmission.idempotency_key,
    firstMountSubmission.idempotency_key
  );
  assert.equal(
    remountedSubmission.requested_pickup_at,
    firstMountSubmission.requested_pickup_at
  );
  assert.equal(Object.isFrozen(firstMountSubmission), true);
  assert.equal(Object.isFrozen(firstMountSubmission.lines[0]), true);
});

test("changed checkout after remount receives a new idempotency key", async () => {
  const storage = createSessionStorage();
  const payload = buildPendingOrderRequest({
    contact: {
      name: "Jessie Guest",
      email: "jessie@example.com",
      phone: "+15551234567",
    },
    idempotencyKey: "",
    lines: [resolvedLine()],
    notes: "",
    requestedPickupAt: "2026-07-28T12:30:00.000Z",
  });
  const first = await prepareOrderSubmission(payload, { storage });
  const changed = await prepareOrderSubmission(
    { ...payload, notes: "Changed after remount" },
    { storage }
  );

  assert.notEqual(changed.idempotency_key, first.idempotency_key);

  clearOrderSubmission(storage);
  const afterReset = await prepareOrderSubmission(payload, { storage });
  assert.notEqual(afterReset.idempotency_key, first.idempotency_key);
});
