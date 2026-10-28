import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { after, test } from "node:test";
import { createServer } from "vite";

const vite = await createServer({ appType: "custom", server: { hmr: false, middlewareMode: true } });
const { previewMissingChecks } = await vite.ssrLoadModule("/src/admin/DesignPreviewPage.jsx");
after(() => vite.close());
const source = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("preview guide never shows raw readiness keys and hides activation-only items for prospects", () => {
  const checks = { organization: false, business_profile: true, verified_hostname: false, fulfillment: false, hours: true, catalog: false, published_design: false, payment_connected: false, clover: false };
  assert.deepEqual(previewMissingChecks(checks, false), ["organization", "verified_hostname", "fulfillment", "catalog", "payment_connected"]);
  assert.deepEqual(previewMissingChecks(checks, true), ["catalog"]);
  assert.deepEqual(previewMissingChecks({ clover: false }, false), ["clover"]);
});

test("preview labels every readiness key in plain language", async () => {
  const page = await source("../../src/admin/DesignPreviewPage.jsx");
  for (const key of ["business_profile", "verified_hostname", "fulfillment", "hours", "catalog", "clover", "payment_connected", "organization"]) assert.match(page, new RegExp(`  ${key}:\\["`));
  assert.doesNotMatch(page, /key\.replaceAll\("_"," "\)/);
  assert.match(page, /Checkout is off in the demo\. Request activation when you’re ready\./);
});

test("setup wizard gives prospects a payments explainer and an in-wizard activation request", async () => {
  const wizard = await source("../../src/setup/SetupWizard.jsx");
  assert.match(wizard, /const prospectLabels = \{ \.\.\.labels, payments:"Payments", launch:"Request activation" \}/);
  assert.match(wizard, /isProspect\?<ProspectPaymentStep\/>:<PaymentSetupStep\/>/);
  assert.match(wizard, /isProspect\?<GoLiveActivationPage embedded\/>:<LaunchPage setupMode\/>/);
  assert.match(wizard, /Payments are set up after activation\./);
  assert.doesNotMatch(wizard.slice(wizard.indexOf("function ProspectPaymentStep"), wizard.indexOf("function PaymentSetupStep")), /Connect Clover|getCloverConnectUrl/);
  const activation = await source("../../src/admin/GoLiveActivationPage.jsx");
  assert.match(activation, /export default function GoLiveActivationPage\(\{ embedded = false \}\)/);
  assert.match(activation, /to="\/setup\/brand">Keep editing my demo</);
  const studio = await source("../../src/admin/DesignStudioPage.jsx");
  assert.match(studio, /<Link to="\/setup\/launch">request activation<\/Link>/);
});
