import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const appSource = await readFile(new URL("../../src/App.jsx", import.meta.url), "utf8");
const ownerContextSource = await readFile(
  new URL("../../src/auth/OwnerAuthContext.jsx", import.meta.url),
  "utf8"
);
const mainSource = await readFile(new URL("../../src/main.jsx", import.meta.url), "utf8");
const ownerBoundarySource = await readFile(
  new URL("../../src/auth/OwnerAuthBoundary.jsx", import.meta.url),
  "utf8"
);
const customerAuthSource = await readFile(
  new URL("../../src/pages/CustomerAuthPage.jsx", import.meta.url),
  "utf8"
);
const customerVerifySource = await readFile(
  new URL("../../src/pages/CustomerVerifyPage.jsx", import.meta.url),
  "utf8"
);
const customerResetSource = await readFile(
  new URL("../../src/pages/CustomerResetPage.jsx", import.meta.url),
  "utf8"
);
const customerLayoutSource = await readFile(
  new URL("../../src/layouts/AppLayout.jsx", import.meta.url),
  "utf8"
);
const accountSource = await readFile(
  new URL("../../src/pages/AccountPage.jsx", import.meta.url),
  "utf8"
);

test("customer authentication routes are registered", () => {
  for (const path of [
    "login",
    "register",
    "account",
    "account/verify-email",
    "account/reset-password",
  ]) {
    assert.match(appSource, new RegExp(`path=["']${path.replace("/", "\\/")}["']`));
  }
});

test("primary navigation exposes the authentication-aware customer account flow", () => {
  assert.match(customerLayoutSource, /label: "Account"/);
  assert.match(customerLayoutSource, /session \? "\/account" : "\/account\/sign-in"/);
  assert.doesNotMatch(customerLayoutSource, /label: "Orders"/);
  assert.match(accountSource, />Profile</);
  assert.match(accountSource, />My Orders</);
  assert.match(accountSource, />Logout</);
});

test("owner session lookup remains lazy outside protected owner routes", () => {
  assert.doesNotMatch(mainSource, /OwnerAuthProvider/);
  assert.match(appSource, /OwnerAuthBoundary/);
  assert.match(ownerBoundarySource, /OwnerAuthProvider/);
  assert.doesNotMatch(ownerContextSource, /useEffect/);
  assert.match(ownerContextSource, /fetchOwnerSession\(\)/);
});

test("customer verification failures expose the existing resend flow", () => {
  assert.match(customerAuthSource, /error\.code === "email_verification_required"/);
  assert.match(customerAuthSource, /This email address has not been verified\./);
  assert.match(customerAuthSource, /resendCustomerVerification\(form\.email\)/);
  assert.match(customerAuthSource, /Resend verification email/);
  assert.match(customerVerifySource, /resendCustomerVerification\(email\)/);
  assert.match(customerVerifySource, /error\.code === "verification_invalid"/);
  assert.match(customerVerifySource, /setCanResend\(true\)/);
  assert.match(customerVerifySource, /Resend verification email/);
});

test("customer password recovery detects Supabase fragment sessions", () => {
  assert.match(customerResetSource, /window\.location\.hash/);
  assert.match(customerResetSource, /recoveryParams\.get\("access_token"\)/);
  assert.match(customerResetSource, /Choose a new password/);
});
