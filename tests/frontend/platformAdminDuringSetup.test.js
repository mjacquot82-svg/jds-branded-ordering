import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { canAccessOwnerPath, operationsLinks } from "../../src/auth/ownerProductPermissions.js";

const platformOwner = { role: "owner", app_launched: false, permissions: [], platform_capabilities: ["platform.organizations.read", "platform.organizations.write"], platform_capabilities_loaded: true };
const normalOwner = { role: "owner", app_launched: false, permissions: [], platform_capabilities: [], platform_capabilities_loaded: true };

test("platform path access requires the read capability", () => {
  assert.equal(canAccessOwnerPath(platformOwner, "/admin/platform"), true);
  assert.equal(canAccessOwnerPath(normalOwner, "/admin/platform"), false);
  assert.equal(canAccessOwnerPath({ ...normalOwner, role: "manager" }, "/admin/platform"), false);
});

test("Platform admin nav link only shows with the read capability", () => {
  assert.ok(operationsLinks(platformOwner).some((l) => l.to === "/admin/platform" && l.label === "Platform admin"));
  assert.ok(!operationsLinks(normalOwner).some((l) => l.to === "/admin/platform"));
});

test("RequireOwner waits for capabilities and lets platform users past the setup redirect only on /admin/platform", async () => {
  const src = await readFile(new URL("../../src/auth/RequireOwner.jsx", import.meta.url), "utf8");
  const wait = src.indexOf("platformPath && session.platform_capabilities_loaded === false");
  const bypass = src.indexOf("!platformBypass &&");
  const setupRedirect = src.indexOf("Navigate replace to={`/setup/${step}`}");
  assert.ok(wait > 0 && bypass > wait && setupRedirect > bypass, "capability wait must precede the setup redirect");
  assert.match(src, /platformBypass = platformPath && hasPlatformCapability\(session, "platform\.organizations\.read"\)/);
});

test("setup wizard shows a Platform admin link only for platform readers", async () => {
  const src = await readFile(new URL("../../src/setup/SetupWizard.jsx", import.meta.url), "utf8");
  const links = src.match(/hasPlatformCapability\(session,"platform\.organizations\.read"\)\?<Link[^>]*to="\/admin\/platform">Platform admin<\/Link>:null/g) || [];
  assert.equal(links.length, 2);
});
