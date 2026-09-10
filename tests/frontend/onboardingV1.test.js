import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { ownerEntryPath } from "../../src/auth/ownerAuthRouting.js";

const onboarding = readFileSync(new URL("../../src/admin/OnboardingPage.jsx", import.meta.url), "utf8");
const studio = readFileSync(new URL("../../src/admin/DesignStudioPage.jsx", import.meta.url), "utf8");
const app = readFileSync(new URL("../../src/App.jsx", import.meta.url), "utf8");
const navigation = readFileSync(new URL("../../src/auth/ownerProductPermissions.js", import.meta.url), "utf8");
const products = readFileSync(new URL("../../src/admin/ProductsPage.jsx", import.meta.url), "utf8");
const scheduling = readFileSync(new URL("../../src/admin/SchedulingPage.jsx", import.meta.url), "utf8");
const launch = readFileSync(new URL("../../src/admin/LaunchPage.jsx", import.meta.url), "utf8");
const preview = readFileSync(new URL("../../src/admin/DesignPreviewPage.jsx", import.meta.url), "utf8");
const wizard = readFileSync(new URL("../../src/setup/SetupWizard.jsx", import.meta.url), "utf8");
const setupGate = readFileSync(new URL("../../src/auth/RequireSetup.jsx", import.meta.url), "utf8");
const ownerGate = readFileSync(new URL("../../src/auth/RequireOwner.jsx", import.meta.url), "utf8");
const layout = readFileSync(new URL("../../src/layouts/AppLayout.jsx", import.meta.url), "utf8");
const activation = readFileSync(new URL("../../src/admin/MerchantActivationPage.jsx", import.meta.url), "utf8");

test("first login enters app building only for a server-reported unlaunched business", () => {
  assert.equal(ownerEntryPath({ role:"owner", app_launched: false }), "/setup/welcome");
  assert.equal(ownerEntryPath({ role:"manager", app_launched: false, onboarding_current_step:"brand" }), "/setup/brand");
  assert.equal(ownerEntryPath({ role:"owner", app_launched: true }), "/admin");
  assert.equal(ownerEntryPath({ role:"owner", app_launched: false }, "/admin/orders"), "/setup/welcome");
  assert.equal(ownerEntryPath({ role:"staff", app_launched: false }, "/admin/orders"), "/admin/orders");
  assert.match(app, /path="setup\/:step\?" element=\{<SetupWizard \/>\}/);
  assert.match(ownerGate, /session\?\.app_launched === false/);
  assert.match(ownerGate, /<Navigate replace to=\{`\/setup\/\$\{step\}`\}/);
  assert.match(setupGate, /session\?\.app_launched/);
  assert.match(layout, /if \(setupWizard\) return/);
});

test("merchant journey is design-first, resumable, and readiness-derived", () => {
  for (const area of ["look","brand","business","catalog","ordering","payments","preview","launch"]) assert.match(onboarding,new RegExp(`key:\"${area}\"`));
  assert.match(onboarding, /fetchOnboarding/);
  assert.match(onboarding, /fetchReadiness/);
  assert.match(onboarding, /recheckReadiness/);
  assert.match(onboarding, /These checks come from your saved app/);
  assert.doesNotMatch(onboarding, /onChange=.*completedSteps/);
});

test("full-screen wizard begins with Welcome and saves server-backed position", () => {
  assert.match(wizard, /Let’s build your ordering app/);
  assert.match(wizard, />Get started</);
  assert.match(wizard, /checkpoint\("look"\)/);
  assert.match(wizard, /saveOnboarding/);
  assert.match(wizard, /Save &amp; exit/);
  assert.match(wizard, />Back</);
  assert.match(wizard, /DesignStudioPage guided wizardStep="look"/);
  assert.match(wizard, /ProductsPage setupMode/);
  assert.match(wizard, /SchedulingPage setupMode/);
  assert.match(wizard, /DesignPreviewPage setupMode/);
  assert.match(wizard, /LaunchPage setupMode/);
});

test("new merchant activation is a full-screen account-access step before the builder", () => {
  assert.match(app, /path="activate" element=\{<MerchantActivationPage \/>\}/);
  assert.match(activation, /Ready to build your ordering app/);
  assert.match(activation, /Build my app/);
  assert.match(activation, /history\?\.replaceState/);
  assert.match(activation, /ownerEntryPath\(next\)/);
  assert.match(layout, /pathname === "\/activate"/);
});

test("guided Design Studio starts with visual app layouts and keeps a live phone preview", () => {
  assert.match(studio, /Let’s build your ordering app/);
  assert.match(studio, /Choose your app layout/);
  assert.match(studio, /layoutChoices\.map/);
  assert.match(studio, /selectLayout\(item\.id\)/);
  assert.match(studio, /LayoutPhonePreview/);
  assert.match(studio, /mobileView/);
});

test("later stages compose existing menu, ordering, payment, preview, and launch systems", () => {
  assert.match(products, /Start by creating a category, then add the first item customers can order/);
  assert.match(scheduling, /Manage when customers can order and when pickups are available/);
  assert.match(wizard, /Connect your payment provider so customer payments flow securely/);
  assert.match(wizard, /Clover is available now/);
  assert.match(wizard, /Payment connection is simulated in this review environment/);
  assert.match(preview, /Preview only — customers can’t order here/);
  assert.match(preview, /Add at least one menu item/);
  assert.match(launch, /launchMerchant/);
  assert.match(launch, /initialSetupCompletedAt/);
  assert.match(launch, /Everything here is checked against your saved app/);
});

test("Design Studio stays prominent after launch and setup remains reachable", () => {
  assert.match(navigation, /Design Studio/);
  assert.match(navigation, /Setup & readiness/);
  assert.match(navigation, /Build your app/);
});
