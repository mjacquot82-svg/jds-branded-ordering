import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { businessNameSlug, customizeBusinessSlug, initialBusinessDetails, merchantAppAddress, updateBusinessName } from "../../src/setup/businessDetails.js";

const page = readFileSync(new URL("../../src/admin/OnboardingPage.jsx", import.meta.url), "utf8");

test("Step 3 derives safe web-address suggestions until the merchant customizes one", () => {
  assert.equal(businessNameSlug("Marc's Drip"), "marcs-drip");
  assert.equal(businessNameSlug("  Café & Pantry!!!  "), "cafe-pantry");
  let state=initialBusinessDetails({display_name:"Marc's Drip"},{slug:"new-merchant-demo",slugIsSuggestion:true});
  assert.equal(state.slug,"marcs-drip");
  state=updateBusinessName(state,"Marc's Coffee");
  assert.equal(state.slug,"marcs-coffee");
  state=customizeBusinessSlug(state,"marcs-special-orders");
  state=updateBusinessName(state,"Marc's Roastery");
  assert.equal(state.slug,"marcs-special-orders");
});

test("Step 3 keeps a previously chosen authoritative web address", () => {
  const state=initialBusinessDetails({display_name:"Marc's Drip"},{slug:"my-custom-app",slugIsSuggestion:false});
  assert.equal(state.slug,"my-custom-app");
  assert.equal(updateBusinessName(state,"A New Name").slug,"my-custom-app");
});

test("Step 3 presents the standard JDS address without leaking runtime routing", () => {
  assert.equal(merchantAppAddress(businessNameSlug("Marc's Drip"),".order.jdsstudio.ca"),"marcs-drip.order.jdsstudio.ca");
  assert.match(page,/merchantAddressSuffix/);
  assert.doesNotMatch(page,/configuredHostname|storefront\.addressSuffix/);
  assert.doesNotMatch(page.match(/<label>Your app’s web address[\s\S]*?<\/label>/)?.[0]||"",/localhost|Codespaces|github\.dev|5173/);
});

test("Step 3 copy distinguishes required customer-facing details from optional fields", () => {
  assert.match(page,/We already have some of your business details/);
  assert.match(page,/Business or app name/);
  assert.match(page,/Your app’s web address/);
  assert.match(page,/Customers will visit/);
  assert.match(page,/confirm this address is available when you save/);
  for (const label of ["Street address (optional)","City (optional)","Phone (optional)","Customer email (optional)","Instagram page (optional)","Facebook page (optional)","Pickup instructions (optional)"]) assert.match(page,new RegExp(label.replace(/[()]/g,"\\$&")));
  assert.match(page,/The email customers can use to contact your business/);
  assert.match(page,/Example: Pick up at the front counter\. Please have your order number ready\./);
  assert.match(page,/placeholder="https:\/\/instagram.com\/yourbusiness"/);
  assert.match(page,/placeholder="https:\/\/facebook.com\/yourbusiness"/);
});
