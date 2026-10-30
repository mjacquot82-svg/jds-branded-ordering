import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { BETA_NOTICE, PACKAGES, PACKAGE_NOTES, forgetPackage, packagePrice, rememberPackage, rememberedPackage } from "../../src/services/packages.js";

const memory = () => { const m = new Map(); return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k) }; };

test("three CAD packages with prices, Pro extras marked coming soon", () => {
  assert.deepEqual(PACKAGES.map((p) => [p.name, packagePrice(p)]), [["Starter", "$150/month"], ["Plus", "$225/month"], ["Pro", "$300/month"]]);
  assert.equal(PACKAGES[2].features.filter((f) => f.comingSoon).length, 3);
  assert.ok(PACKAGES[0].features.some((f) => f.label === "Refunds"));
  assert.ok(PACKAGE_NOTES.includes("Extra locations: $75/month each"));
  assert.match(BETA_NOTICE, /Free during the beta.*won't be charged.*30 days/);
});

test("the choice survives email verification via local storage, and rejects unknown keys", () => {
  const storage = memory();
  rememberPackage("gold", storage);
  assert.equal(rememberedPackage(storage), null);
  rememberPackage("plus", storage);
  assert.equal(rememberedPackage(storage), "plus");
  forgetPackage(storage);
  assert.equal(rememberedPackage(storage), null);
});

test("/build shows the picker as step 1 and saves the choice; dashboard and platform admin show it", async () => {
  const read = (path) => readFile(new URL(path, import.meta.url), "utf8");
  const build = await read("../../src/pages/BuildStoreLandingPage.jsx");
  assert.match(build, /Step 1: Pick your package/);
  assert.match(build, /saveOwnerPackage\(pending/);
  assert.match(await read("../../src/admin/AdminDashboard.jsx"), /<PackageCard/);
  assert.match(await read("../../src/admin/PlatformAdminPage.jsx"), /packageName\(item\.selectedPackage\)/);
  assert.match(await read("../../src/components/PackagePicker.jsx"), /Coming soon/);
});
