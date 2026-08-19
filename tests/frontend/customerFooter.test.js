import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const layout = await readFile(
  new URL("../../src/layouts/AppLayout.jsx", import.meta.url),
  "utf8"
);

test("customer shell displays the approved JDS footer and URL", () => {
  assert.match(
    layout,
    /Jacquot Digital Solutions · Walkerton, Ont\. ·\{" "\}[\s\S]*?href="https:\/\/jdsstudio\.ca"[\s\S]*?>\s*jdsstudio\.ca\s*</
  );
  assert.match(layout, /rel="noopener noreferrer"/);
  assert.match(layout, /target="_blank"/);
});

test("customer footer excludes every operational portal route family", () => {
  assert.match(
    layout,
    /const operationalPathPrefixes = \["\/admin", "\/owner", "\/staff", "\/kitchen"\]/
  );
  assert.match(layout, /pathname === prefix \|\| pathname\.startsWith\(`\$\{prefix\}\/`\)/);
  assert.match(layout, /\{showCustomerFooter \? \([\s\S]*?<footer className="customer-footer">/);
});

test("customer account and authentication routes remain in the shared customer shell", async () => {
  const app = await readFile(new URL("../../src/App.jsx", import.meta.url), "utf8");
  const customerRouteBlock = app.slice(
    app.indexOf('<Route element={<AppLayout />}>'),
    app.indexOf('<Route element={<OwnerAuthBoundary />}>')
  );

  for (const path of [
    "account",
    "login",
    "register",
    "account/sign-in",
    "account/create",
    "account/verify-email",
    "account/reset-password",
  ]) {
    assert.match(customerRouteBlock, new RegExp(`path="${path.replaceAll("/", "\\/")}"`));
  }
});
