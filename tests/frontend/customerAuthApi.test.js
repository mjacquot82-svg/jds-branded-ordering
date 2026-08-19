import assert from "node:assert/strict";
import test from "node:test";

import {
  completeCustomerPasswordReset, fetchCustomerSession, loginCustomer, logoutCustomer, registerCustomer,
  resendCustomerVerification,
} from "../../src/services/customerAuthApi.js";

function response(status, payload) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

test("customer auth uses credentialed JDS sessions without browser tokens", async () => {
  const calls = [];
  const fetchImpl = async (...args) => {
    calls.push(args);
    return response(200, { role: "customer", csrf_token: "csrf" });
  };
  await fetchCustomerSession({ fetchImpl });
  await loginCustomer("customer@example.com", "long password", { fetchImpl, keepSignedIn: true });
  await logoutCustomer("csrf", { fetchImpl });
  assert.equal(calls[0][0], "/api/v1/customer/auth/session");
  assert.equal(calls[0][1].credentials, "include");
  assert.deepEqual(JSON.parse(calls[1][1].body), { email: "customer@example.com", keep_signed_in: true, password: "long password" });
  assert.equal(calls[2][1].headers["X-CSRF-Token"], "csrf");
});

test("customer login defaults to the existing non-persistent session", async () => {
  let request;
  await loginCustomer("customer@example.com", "long password", {
    fetchImpl: async (...args) => { request = args; return response(200, { role: "customer" }); },
  });
  assert.equal(JSON.parse(request[1].body).keep_signed_in, false);
});

test("verification resend uses the generic customer auth endpoint", async () => {
  let request;
  await resendCustomerVerification("customer@example.com", {
    fetchImpl: async (...args) => { request = args; return response(200, { message: "Sent" }); },
  });
  assert.equal(request[0], "/api/v1/customer/auth/verification/resend");
  assert.deepEqual(JSON.parse(request[1].body), { email: "customer@example.com" });
});

test("password reset completion sends a Supabase recovery access token", async () => {
  let request;
  await completeCustomerPasswordReset({
    accessToken: "recovery-access-token",
    password: "a sufficiently long password",
  }, {
    fetchImpl: async (...args) => { request = args; return response(200, { message: "Updated" }); },
  });
  assert.equal(request[0], "/api/v1/customer/auth/password-reset/complete");
  assert.deepEqual(JSON.parse(request[1].body), {
    access_token: "recovery-access-token",
    password: "a sufficiently long password",
  });
});

test("customer registration sends profile identity and normalized phone to the shared auth backend", async () => {
  let request;
  await registerCustomer("Customer Name", "customer@example.com", "a sufficiently long password", "+15198816869", {
    fetchImpl: async (...args) => { request = args; return response(201, { message: "Verify" }); },
  });
  assert.equal(request[0], "/api/v1/customer/auth/register");
  assert.deepEqual(JSON.parse(request[1].body), {
    display_name: "Customer Name", email: "customer@example.com", password: "a sufficiently long password", phone: "+15198816869",
  });
});
