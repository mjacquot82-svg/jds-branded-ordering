import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const onboarding = readFileSync(new URL("../../src/admin/OnboardingPage.jsx", import.meta.url), "utf8");

test("merchant onboarding is guided, resumable, and server-verified", () => {
  for (const area of ["business", "storefront", "hours", "fulfillment", "design", "catalog", "clover"]) {
    assert.match(onboarding, new RegExp(`key:\"${area}\"`));
  }
  assert.match(onboarding, /Recommended next step/);
  assert.match(onboarding, /fetchOnboarding/);
  assert.match(onboarding, /recheckReadiness/);
  assert.match(onboarding, /Your storefront stays private until JDS readiness checks pass/);
  assert.doesNotMatch(onboarding, /checked=\{completed\.has\(key\)\}[^>]*onChange/);
});
