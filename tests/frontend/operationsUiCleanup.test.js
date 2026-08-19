import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { lunchSpecialAnnouncement } from "../../src/services/announcementFormatting.js";

test("Operations logout has one shared lifecycle-controlled navigation path", async () => {
  const boundary = await readFile(new URL("../../src/auth/RequireOwner.jsx", import.meta.url), "utf8");
  const dashboard = await readFile(new URL("../../src/admin/AdminDashboard.jsx", import.meta.url), "utf8");

  assert.match(boundary, /const \[logoutDestination, setLogoutDestination\] = useState\(null\)/);
  assert.match(boundary, /const destination = session\?\.role === "staff" \? "\/staff" : "\/owner\/login"/);
  assert.match(boundary, /logoutDestination && !session && status === "anonymous"/);
  assert.match(boundary, /<Navigate replace to=\{logoutDestination\}/);
  assert.doesNotMatch(boundary, /useNavigate|navigate\(destination/);
  assert.match(boundary, /secondary-button operations-nav-signout/);
  assert.doesNotMatch(dashboard, /handleLogout|LogOut|> Sign out<|logout,/);
});

test("Owner and Staff login pages present symmetrical alternate access buttons", async () => {
  const ownerLogin = await readFile(new URL("../../src/admin/OwnerLoginPage.jsx", import.meta.url), "utf8");
  const staffLogin = await readFile(new URL("../../src/admin/StaffLoginPage.jsx", import.meta.url), "utf8");

  assert.match(ownerLogin, /login-action-row/);
  assert.match(ownerLogin, /className="secondary-button" to="\/staff">Staff Access/);
  assert.match(staffLogin, /login-action-row/);
  assert.match(staffLogin, /className="secondary-button" to="\/owner\/login">Owner sign in/);
});

test("Lunch Special announcement always formats authoritative product data", () => {
  assert.equal(
    lunchSpecialAnnouncement({ name: "Buffalo Chickpea Bowl", price_cents: 1295 }),
    "Today’s Lunch Special is Buffalo Chickpea Bowl for $12.95. Order online while it’s available!",
  );
  assert.equal(
    lunchSpecialAnnouncement({ name: "Buffalo Chickpea Bowl", price_cents: 1195 }),
    "Today’s Lunch Special is Buffalo Chickpea Bowl for $11.95. Order online while it’s available!",
  );
  assert.equal(lunchSpecialAnnouncement(null), "");
});

test("Lunch Special is read-only while the Owner General Announcement remains editable", async () => {
  const communications = await readFile(new URL("../../src/admin/CommunicationsPage.jsx", import.meta.url), "utf8");

  assert.match(communications, /<LunchSpecialPreview[^>]*message=\{lunchMessage\}/);
  assert.match(communications, /System generated/);
  assert.doesNotMatch(communications, /setLunchMessage|onMessageChange=\{setLunchMessage\}/);
  assert.match(communications, /owner \? <section[^>]*general-announcement-heading/);
  assert.match(communications, /message=\{generalMessage\} onMessageChange=\{setGeneralMessage\}/);
});
