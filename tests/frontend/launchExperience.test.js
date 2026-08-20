import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const launch = readFileSync(new URL("../../src/admin/LaunchPage.jsx", import.meta.url), "utf8");
const permissions = readFileSync(new URL("../../src/auth/ownerProductPermissions.js", import.meta.url), "utf8");

test("merchant launch area is readiness-gated and provides practical assets", () => {
  assert.match(launch, /fetchReadiness/);
  assert.match(launch, /if\(readiness\.publicReady\)/);
  assert.match(launch, /Download QR code/);
  assert.match(launch, /Open printable sign/);
  assert.match(launch, /subscriptionMessages/);
  assert.match(permissions, /label: "Launch"/);
});
