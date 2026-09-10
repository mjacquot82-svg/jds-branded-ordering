import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("demo /build routes bypass hard storefront hostname failure", async () => {
  const source = await readFile(new URL("../../src/tenant/TenantContext.jsx", import.meta.url), "utf8");
  assert.match(source, /\/\(admin\|owner\|staff\|build\|activate\|setup\|go-live\)/);
  assert.match(source, /self-service demo funnel/);
});

test("build landing uses setup-style shell without customer storefront chrome", async () => {
  const layout = await readFile(new URL("../../src/layouts/AppLayout.jsx", import.meta.url), "utf8");
  assert.match(layout, /pathname === "\/build" \|\| pathname\.startsWith\("\/build\/"\)/);
});
