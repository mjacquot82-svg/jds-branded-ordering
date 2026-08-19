import assert from "node:assert/strict";
import test from "node:test";

import {
  createOwnerClosure,
  fetchOwnerScheduling,
  updateOwnerHours,
  updateOwnerOrdering,
} from "../../src/services/ownerSchedulingApi.js";

function jsonResponse(status, payload) {
  return { ok: status >= 200 && status < 300, status, async json() { return payload; } };
}

test("owner scheduling reads the protected production configuration", async () => {
  let request;
  const payload = { ordering_mode: "schedule", hours: [], closures: [], preview: {} };
  assert.deepEqual(await fetchOwnerScheduling({
    apiBaseUrl: "https://api.example.test/",
    fetchImpl: async (...args) => { request = args; return jsonResponse(200, payload); },
  }), payload);
  assert.equal(request[0], "https://api.example.test/api/v1/owner/scheduling");
  assert.equal(request[1].credentials, "include");
  assert.equal(request[1].method, "GET");
});

test("owner scheduling mutations send CSRF and owner-friendly values", async () => {
  const calls = [];
  const fetchImpl = async (...args) => { calls.push(args); return jsonResponse(200, { preview: {} }); };
  await updateOwnerOrdering("force_closed", "csrf", { fetchImpl });
  await updateOwnerHours([{ weekday: 0, is_closed: true, opens_at: null, closes_at: null }], "csrf", { fetchImpl });
  await createOwnerClosure({ business_date: "2026-12-25", reopens_on: null, reason: "Christmas Day" }, "csrf", { fetchImpl });

  assert.deepEqual(JSON.parse(calls[0][1].body), { ordering_mode: "force_closed" });
  assert.equal(calls[0][1].headers["X-CSRF-Token"], "csrf");
  assert.deepEqual(JSON.parse(calls[1][1].body), { hours: [{ weekday: 0, is_closed: true, opens_at: null, closes_at: null }] });
  assert.deepEqual(JSON.parse(calls[2][1].body), { business_date: "2026-12-25", reopens_on: null, reason: "Christmas Day" });
});
