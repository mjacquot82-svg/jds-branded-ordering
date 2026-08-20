import assert from "node:assert/strict";
import test from "node:test";

import { localReviewForwarding, localReviewProxy } from "../../vite.local-review-proxy.js";

test("Codespaces local review proxy replaces routing headers with exact trusted values", () => {
  const origin = "https://synthetic-codespace-5173.app.github.dev";
  const listeners = new Map();
  const headers = new Map();
  const proxy = { on(event, listener) { listeners.set(event, listener); } };
  const proxyRequest = { setHeader(name, value) { headers.set(name.toLowerCase(), value); } };

  localReviewProxy("http://127.0.0.1:8000", origin).configure(proxy);
  listeners.get("proxyReq")(proxyRequest);

  assert.deepEqual(Object.fromEntries(headers), {
    origin: "https://synthetic-codespace-5173.app.github.dev",
    "x-forwarded-host": "synthetic-codespace-5173.app.github.dev",
    "x-forwarded-proto": "https",
    forwarded: 'for=127.0.0.1;host="synthetic-codespace-5173.app.github.dev";proto=https',
  });
});

test("local review forwarding is opt-in and rejects non-HTTPS origins", () => {
  assert.equal(localReviewForwarding(""), null);
  assert.throws(
    () => localReviewForwarding("http://attacker.example"),
    /must be an HTTPS origin/,
  );
});
