import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { withInstalledAppDefaults } from "../../src/design/installedAppDefaults.js";

test("a freshly loaded design is compared against its normalized form, so it is not falsely unsaved", async () => {
  const page = await readFile(new URL("../../src/admin/DesignStudioPage.jsx", import.meta.url), "utf8");
  assert.match(page, /const loadedConfig=withInstalledAppDefaults\(value\.config\);setDraft\(\{\.\.\.value,config:loadedConfig\}\);setSavedConfig\(loadedConfig\)/);
  const legacy = { displayName: "Harbor & Hearth Café", heroContent: "tagline-cta", colors: { primary: "#4a5d4e", background: "#f6f1ea" }, pwa: { shortName: "Harbor", themeColor: "#4a5d4e", backgroundColor: "#f6f1ea" }, branding: { showLogo: true, showHero: true, headerMode: "tagline" } };
  const once = withInstalledAppDefaults(legacy);
  assert.equal(once.heroContent, "cta");
  assert.deepEqual(withInstalledAppDefaults(once), once); // idempotent: reload → still "saved"
});
