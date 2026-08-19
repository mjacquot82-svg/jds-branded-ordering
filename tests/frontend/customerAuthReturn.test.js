import assert from "node:assert/strict";
import test from "node:test";

import {
  clearCustomerReturn,
  customerAuthHref,
  customerReturnFrom,
  rememberCustomerReturn,
  safeCustomerReturn,
} from "../../src/services/customerAuthReturn.js";

function storage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  };
}

test("checkout auth continuation accepts only Cart and survives registration verification", () => {
  const store = storage();
  assert.equal(rememberCustomerReturn("/cart", store), "/cart");
  assert.equal(customerReturnFrom(new URLSearchParams(), store), "/cart");
  assert.equal(customerAuthHref("/account/sign-in", "/cart"), "/account/sign-in?returnTo=%2Fcart");
  clearCustomerReturn(store);
  assert.equal(customerReturnFrom(new URLSearchParams(), store), "/account");
});

test("checkout auth continuation rejects external and unrelated destinations", () => {
  for (const value of ["https://evil.example", "//evil.example", "/admin", "/menu", null]) {
    assert.equal(safeCustomerReturn(value), "/account");
  }
  assert.equal(customerAuthHref("/login", "/admin"), "/login");
});
