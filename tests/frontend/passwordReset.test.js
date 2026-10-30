import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { NEUTRAL_RESET_MESSAGE, passwordProblem, readRecoveryCredential } from "../../src/auth/passwordReset.js";
import { completeOwnerPasswordReset, requestOwnerPasswordReset } from "../../src/services/ownerAuthApi.js";

const ok = (payload) => ({ ok: true, status: 200, async json() { return payload; } });

test("recovery links: token_hash query or Supabase #access_token fragment", () => {
  assert.deepEqual(readRecoveryCredential("?token_hash=abc", ""), { tokenHash: "abc", accessToken: null, error: null });
  assert.equal(readRecoveryCredential("", "#access_token=xyz&type=recovery").accessToken, "xyz");
  assert.ok(readRecoveryCredential("", "#error=access_denied&error_description=expired").error);
});

test("password rules: minimum length and matching confirm", () => {
  assert.match(passwordProblem("short", "short", 15), /at least 15/);
  assert.match(passwordProblem("a long enough passphrase", "different one here", 15), /match/);
  assert.equal(passwordProblem("a long enough passphrase", "a long enough passphrase", 15), "");
});

test("owner reset API calls the owner auth endpoints", async () => {
  const calls = [];
  const fetchImpl = async (...args) => { calls.push(args); return ok({ message: "x" }); };
  await requestOwnerPasswordReset("a@b.co", { apiBaseUrl: "https://api.test", fetchImpl });
  await completeOwnerPasswordReset({ accessToken: "tok", password: "p" }, { apiBaseUrl: "https://api.test", fetchImpl });
  assert.equal(calls[0][0], "https://api.test/api/v1/owner/auth/password-reset");
  assert.deepEqual(JSON.parse(calls[0][1].body), { email: "a@b.co" });
  assert.equal(calls[1][0], "https://api.test/api/v1/owner/auth/password-reset/complete");
  assert.deepEqual(JSON.parse(calls[1][1].body), { access_token: "tok", password: "p" });
});

test("owner login links to /reset-password and the route exists", async () => {
  const login = await readFile(new URL("../../src/admin/OwnerLoginPage.jsx", import.meta.url), "utf8");
  const app = await readFile(new URL("../../src/App.jsx", import.meta.url), "utf8");
  const page = await readFile(new URL("../../src/pages/PasswordResetPage.jsx", import.meta.url), "utf8");
  assert.match(login, /to="\/reset-password">Forgot password\?/);
  assert.match(app, /path="reset-password"/);
  assert.match(page, /Confirm new password/);
  assert.match(NEUTRAL_RESET_MESSAGE, /^If an account exists, we've sent a link/);
});
