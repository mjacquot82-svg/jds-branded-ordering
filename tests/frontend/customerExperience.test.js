import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { getApiErrorMessage, getCustomerErrorMessage } from "../../src/services/customerMessages.js";
import { formatCustomerPhone, isCompleteCustomerPhone, normalizeCustomerPhone } from "../../src/services/customerPhone.js";

const authPageSource = await readFile(new URL("../../src/pages/CustomerAuthPage.jsx", import.meta.url), "utf8");
const resetPageSource = await readFile(new URL("../../src/pages/CustomerResetPage.jsx", import.meta.url), "utf8");
const verifyPageSource = await readFile(new URL("../../src/pages/CustomerVerifyPage.jsx", import.meta.url), "utf8");
const accountPageSource = await readFile(new URL("../../src/pages/AccountPage.jsx", import.meta.url), "utf8");
const cartPageSource = await readFile(new URL("../../src/pages/CartPage.jsx", import.meta.url), "utf8");

test("customer phone input formats progressively and normalizes to E.164", () => {
  assert.equal(formatCustomerPhone("519"), "519");
  assert.equal(formatCustomerPhone("519881"), "(519) 881");
  assert.equal(formatCustomerPhone("5198816869"), "(519) 881-6869");
  assert.equal(formatCustomerPhone("+1 (519) 881-6869"), "(519) 881-6869");
  assert.equal(normalizeCustomerPhone("(519) 881-6869"), "+15198816869");
  assert.equal(isCompleteCustomerPhone("519881686"), false);
  assert.equal(isCompleteCustomerPhone("5198816869"), true);
});

test("customer errors never stringify structured objects", () => {
  const fallback = "Please try again.";
  assert.equal(getApiErrorMessage({ detail: [{ msg: "invalid" }] }, fallback), fallback);
  assert.equal(getApiErrorMessage({ detail: { message: "Check your phone." } }, fallback), "Check your phone.");
  assert.equal(getCustomerErrorMessage({ message: "[object Object]" }, fallback), fallback);
  assert.equal(getCustomerErrorMessage({ message: { unsafe: true } }, fallback), fallback);
});

test("customer forms default persistence and expose guarded pending states", () => {
  assert.match(authPageSource, /useState\(true\)/);
  assert.match(authPageSource, /disabled=\{isSubmitting \|\| isResending\}/);
  assert.match(authPageSource, /Creating account…/);
  assert.match(authPageSource, /Signing in…/);
  assert.match(resetPageSource, /disabled=\{isSubmitting\}/);
  assert.match(resetPageSource, /Updating…/);
  assert.match(verifyPageSource, /disabled=\{isResending\}/);
  assert.match(accountPageSource, /disabled=\{isSaving\}/);
  assert.match(cartPageSource, /disabled=\{checkoutLocked\}/);
  assert.doesNotMatch(cartPageSource, /disabled=\{isPlacingOrder \|\| !canPlaceOrder\}/);
  assert.match(cartPageSource, /aria-busy=\{isPlacingOrder\}/);
  assert.match(cartPageSource, /Placing order…/);
  assert.match(cartPageSource, /Your order is already being submitted\. Please wait\./);
  assert.match(cartPageSource, /Add your first and last name, email, and phone number before placing your order\./);
  assert.match(cartPageSource, /if \(!orderingCustomer\) \{/);
  assert.match(cartPageSource, /Sign in to place your order/);
  assert.match(cartPageSource, /Your café bag is saved/);
  assert.match(cartPageSource, /\/account\/sign-in\?returnTo=%2Fcart/);
  assert.match(cartPageSource, /\/account\/create\?returnTo=%2Fcart/);
  assert.doesNotMatch(cartPageSource, /Continue as Guest/);
  assert.match(cartPageSource, /isOrderingCustomerSession\(session\)/);
  assert.match(authPageSource, /Ordering requires a customer account/);
});

test("customer registration and recovery require 10-character passwords", () => {
  assert.match(authPageSource, /minLength=\{creating \? 10 : 8\}/);
  assert.match(resetPageSource, /minLength=\{10\}/);
  assert.match(authPageSource, /Use at least 10 characters\./);
  assert.match(resetPageSource, /Use at least 10 characters\./);
});

test("customer password fields have accessible visibility toggles", () => {
  for (const source of [authPageSource, resetPageSource]) {
    assert.match(source, /showPassword/);
    assert.match(source, /Show password/);
    assert.match(source, /Hide password/);
    assert.match(source, /type="button"/);
    assert.match(source, /aria-hidden="true"/);
  }
});

test("saved orders transition checkout to payment-only recovery", () => {
  assert.match(cartPageSource, /setSavedOrder\(order\)/);
  assert.match(cartPageSource, /createCloverCheckout\(savedOrder\.public_token\)/);
  assert.match(cartPageSource, /The café has your order/);
  assert.match(cartPageSource, /Payment needed<\/span><strong>Complete now/);
  assert.match(cartPageSource, /Complete secure payment/);
  assert.doesNotMatch(cartPageSource, /finish checking out/i);
  assert.doesNotMatch(cartPageSource, /Retry payment/);
  assert.match(cartPageSource, /contact the café/);
  assert.match(cartPageSource, /Your order will not be submitted again/);
  assert.doesNotMatch(cartPageSource, /savedOrder && checkoutError/);
  assert.match(cartPageSource, /if \(savedOrder\) \{/);
  assert.match(cartPageSource, /saved-order-details/);
  assert.doesNotMatch(cartPageSource, /className="cart-summary-detail"/);
});

test("checkout renders saved phone data as a controlled value, not a placeholder", () => {
  assert.match(cartPageSource, /phone: formatCustomerPhone\(profile\.phone \|\| ""\)/);
  assert.match(cartPageSource, /value=\{checkoutContact\.phone\}/);
  assert.doesNotMatch(cartPageSource, /placeholder="\(519\) 881-6869"/);
});

test("profile saves exclude the read-only email returned by profile hydration", () => {
  assert.doesNotMatch(accountPageSource, /updateCustomerProfile\(\{ \.\.\.profile/);
  assert.match(accountPageSource, /name: profile\.name/);
  assert.match(accountPageSource, /phone: normalizeCustomerPhone\(profile\.phone\)/);
});

test("checkout cursor styling distinguishes idle, disabled, and submitting states", async () => {
  const styleSource = await readFile(new URL("../../src/style.css", import.meta.url), "utf8");

  assert.match(styleSource, /\.cart-review \.primary-button \{\s*cursor: pointer;/);
  assert.match(styleSource, /\.cart-review \.primary-button:disabled \{\s*cursor: not-allowed;/);
  assert.match(styleSource, /\.cart-review \.primary-button\[aria-busy="true"\] \{\s*cursor: progress;/);
});
