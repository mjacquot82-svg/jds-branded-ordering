import assert from "node:assert/strict";
import test from "node:test";
import { fetchOwnerCommunications, OwnerCommunicationsError } from "../../src/services/ownerCommunicationsApi.js";

const response = (status, payload) => ({ ok: status >= 200 && status < 300, status, json: async () => payload });

test("fetchOwnerCommunications uses the owner session endpoint", async () => {
  let request;
  const payload = {
    summary: { actionable_warnings: 0, push_release_enabled: false },
    lunch_special: null,
    activity: [],
    health: [{ key: "push", status: "not_connected", actionable: false }],
  };
  const result = await fetchOwnerCommunications({ apiBaseUrl: "https://api.example.test/", fetchImpl: async (...args) => { request = args; return response(200, payload); } });
  assert.equal(result, payload);
  assert.equal(request[0], "https://api.example.test/api/v1/owner/communications");
  assert.equal(request[1].credentials, "include");
});

test("fetchOwnerCommunications preserves safe API failures", async () => {
  await assert.rejects(
    fetchOwnerCommunications({ fetchImpl: async () => response(503, { detail: { code: "communications_unavailable", message: "Try again later." } }) }),
    (error) => error instanceof OwnerCommunicationsError && error.code === "communications_unavailable" && error.message === "Try again later.",
  );
});
