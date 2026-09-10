import test from "node:test";
import assert from "node:assert/strict";
import { enterDemo, fetchDemoPricing, signupDemo } from "../../src/services/demoFunnelApi.js";

test("signupDemo posts to /api/v1/demo/signup", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: true,
      async json() {
        return { status: "ready", session: { role: "owner" }, commercialMode: "prospect" };
      },
    };
  };
  const result = await signupDemo(
    { email: "a@example.com", password: "password1234", business_name: "Demo Café" },
    { fetchImpl, apiBaseUrl: "http://api.test" },
  );
  assert.equal(result.status, "ready");
  assert.equal(calls[0].url, "http://api.test/api/v1/demo/signup");
  assert.equal(calls[0].init.method, "POST");
});

test("fetchDemoPricing reads public pricing", async () => {
  const fetchImpl = async () => ({
    ok: true,
    async json() {
      return { amountCents: 15000, jdsSalesTakePercent: 0, currency: "CAD" };
    },
  });
  const pricing = await fetchDemoPricing({ fetchImpl, apiBaseUrl: "" });
  assert.equal(pricing.amountCents, 15000);
  assert.equal(pricing.jdsSalesTakePercent, 0);
});

test("enterDemo posts credentials", async () => {
  const fetchImpl = async (url, init) => {
    assert.match(url, /\/api\/v1\/demo\/enter$/);
    assert.equal(init.method, "POST");
    return { ok: true, async json() { return { status: "verification_required" }; } };
  };
  const result = await enterDemo({ email: "a@example.com", password: "password1234" }, { fetchImpl });
  assert.equal(result.status, "verification_required");
});
