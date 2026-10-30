import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  describeSquareConnection,
  fetchSquareConnection,
  getSquareConnectUrl,
  refreshSquarePaymentStatus,
  SquareConnectionError,
  squareReturnMessage,
} from "../../src/services/squareService.js";

const read = (path) => readFile(new URL(`../../${path}`, import.meta.url), "utf8");

test("Square connect URL uses the PR #22 OAuth start route", () => {
  assert.equal(getSquareConnectUrl("https://api.example.test/"), "https://api.example.test/api/v1/square/oauth/start");
});

test("Square connection status is described in plain words, including reconnect", () => {
  assert.equal(describeSquareConnection({ connected: true, health: "healthy", environment: "sandbox" }).detail,
    "Customers can pay by card through Square (test mode).");
  assert.equal(describeSquareConnection({ connected: false, health: "reconnect_required" }).heading, "Reconnect needed");
  assert.equal(describeSquareConnection({ connected: false, health: "no_location" }).heading, "No active location");
  assert.equal(describeSquareConnection({ connected: false, health: "disconnected" }).heading, "Not connected");
  assert.equal(squareReturnMessage("connected"), "Square is connected.");
  assert.match(squareReturnMessage("cancelled"), /wasn’t connected/);
  assert.equal(squareReturnMessage(null), "");
});

test("fetchSquareConnection surfaces auth errors and sends credentials", async () => {
  let seen;
  const ok = await fetchSquareConnection({ apiBaseUrl: "https://api.test", fetchImpl: async (url, init) => {
    seen = { url, init };
    return { ok: true, status: 200, json: async () => ({ configured: true, connected: true, health: "healthy" }) };
  } });
  assert.equal(seen.url, "https://api.test/api/v1/square/connection");
  assert.equal(seen.init.credentials, "include");
  assert.equal(ok.connected, true);
  await assert.rejects(
    fetchSquareConnection({ fetchImpl: async () => ({ ok: false, status: 401, json: async () => ({ detail: { code: "x" } }) }) }),
    (error) => error instanceof SquareConnectionError && error.status === 401,
  );
});

test("refreshSquarePaymentStatus posts to the status check and never throws", async () => {
  let seen;
  const paid = await refreshSquarePaymentStatus("tok/1", { apiBaseUrl: "", fetchImpl: async (url, init) => {
    seen = { url, init };
    return { ok: true, json: async () => ({ paid: true }) };
  } });
  assert.equal(seen.url, "/api/v1/square/orders/tok%2F1/refresh");
  assert.equal(seen.init.method, "POST");
  assert.equal(paid.paid, true);
  assert.deepEqual(await refreshSquarePaymentStatus("t", { fetchImpl: async () => { throw new Error("down"); } }), { paid: false });
  assert.deepEqual(await refreshSquarePaymentStatus("t", { fetchImpl: async () => ({ ok: false }) }), { paid: false });
});

test("setup wizard offers Connect Square only when Square is set up, Clover button unchanged", async () => {
  const wizard = await read("src/setup/SetupWizard.jsx");
  assert.match(wizard, /squareAvailable=readiness\.paymentOptions\?\.squareAvailable===true/);
  assert.match(wizard, /squareAvailable&&\(!ready\|\|squareNeedsReconnect\)\?<a className="secondary-button" href=\{getSquareConnectUrl\(\)\}>/);
  assert.match(wizard, /cloverAvailable&&!ready\?<a className="secondary-button" href=\{getCloverConnectUrl\(\)\}>Connect Clover<\/a>/);
});

test("owner dashboard shows a Square card with reconnect, hidden when Square isn't set up", async () => {
  const dashboard = await read("src/admin/AdminDashboard.jsx");
  assert.match(dashboard, /squareHidden = square\.status === "unavailable"/);
  assert.match(dashboard, /"Reconnect Square" : "Connect Square"/);
  assert.match(dashboard, /<span>Clover<\/span>/);
});

test("confirmation page checks Square directly while waiting and names the right provider", async () => {
  const page = await read("src/pages/ConfirmationPage.jsx");
  assert.match(page, /searchParams\.get\("provider"\) === "square"/);
  assert.match(page, /await refreshSquarePaymentStatus\(publicToken\)/);
  assert.doesNotMatch(page, /"Clover could not complete/);
  assert.match(page, /\$\{providerName\} returned you to the shop/);
});

test("platform admin is provider-aware", async () => {
  const page = await read("src/admin/PlatformAdminPage.jsx");
  assert.match(page, /<th>Payments<\/th>/);
  assert.match(page, /item\.paymentProvider==="square"/);
  assert.match(page, /detail\.square\?\.length/);
});
