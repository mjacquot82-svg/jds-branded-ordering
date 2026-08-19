import assert from "node:assert/strict";
import { after, test } from "node:test";

import { JSDOM } from "jsdom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const vite = await createServer({ appType: "custom", server: { hmr: false, middlewareMode: true } });
const [{ OwnerAuthProvider }, { default: RequireOwner }, { default: OwnerLoginPage }, { default: StaffLoginPage }] = await Promise.all([
  vite.ssrLoadModule("/src/auth/OwnerAuthContext.jsx"),
  vite.ssrLoadModule("/src/auth/RequireOwner.jsx"),
  vite.ssrLoadModule("/src/admin/OwnerLoginPage.jsx"),
  vite.ssrLoadModule("/src/admin/StaffLoginPage.jsx"),
]);

after(() => vite.close());

const response = (status, payload) => ({
  json: async () => payload,
  ok: status >= 200 && status < 300,
  status,
});

async function waitForText(container, text) {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    if (container.textContent.includes(text)) return;
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
  }
  assert.fail(`Expected rendered application to contain: ${text}\nActual: ${container.textContent}`);
}

async function verifyLogoutRendersLogin({ expectedLogin, role }) {
  const dom = new JSDOM("<!doctype html><html><body><div id=\"root\"></div></body></html>", { url: "https://cafe.test/admin" });
  const previousGlobals = { document: globalThis.document, fetch: globalThis.fetch, window: globalThis.window };
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;

  const session = {
    csrf_token: "csrf-token",
    display_name: role === "staff" ? "Test Staff" : "Test Owner",
    permissions: role === "staff" ? ["orders.read"] : ["*"],
    role,
  };
  let logoutCalls = 0;
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url);
    if (path.endsWith("/api/v1/owner/auth/session")) return response(200, session);
    if (path.endsWith("/api/v1/owner/auth/logout")) {
      assert.equal(options.method, "POST");
      assert.equal(options.headers["X-CSRF-Token"], "csrf-token");
      logoutCalls += 1;
      return response(200, {});
    }
    if (path.endsWith("/api/v1/staff/access/accounts")) return response(200, []);
    throw new Error(`Unexpected request: ${path}`);
  };

  const container = document.getElementById("root");
  const root = createRoot(container);
  try {
    await act(async () => {
      root.render(
        React.createElement(
          MemoryRouter,
          { initialEntries: ["/admin"] },
          React.createElement(
            OwnerAuthProvider,
            null,
            React.createElement(
              Routes,
              null,
              React.createElement(
                Route,
                { element: React.createElement(RequireOwner), path: "/admin" },
                React.createElement(Route, { element: React.createElement("h1", null, "Authenticated portal"), index: true }),
              ),
              React.createElement(Route, { element: React.createElement(OwnerLoginPage), path: "/owner/login" }),
              React.createElement(Route, { element: React.createElement(StaffLoginPage), path: "/staff" }),
            ),
          ),
        ),
      );
    });
    await waitForText(container, "Authenticated portal");

    const signOut = [...container.querySelectorAll("button")].find((button) => button.textContent.includes("Sign out"));
    assert.ok(signOut, "Operations Sign out button rendered");
    await act(async () => signOut.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })));

    await waitForText(container, expectedLogin);
    assert.equal(logoutCalls, 1, "server-side session revocation was requested once");
    assert.ok(container.querySelector("form"), "login form rendered in the existing SPA root");
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
    globalThis.window = previousGlobals.window;
    globalThis.document = previousGlobals.document;
    globalThis.fetch = previousGlobals.fetch;
  }
}

test("Owner logout renders Owner sign in without remounting the SPA", { concurrency: false }, () => verifyLogoutRendersLogin({
  expectedLogin: "Owner sign in",
  role: "owner",
}));

test("Staff logout renders Staff Access without remounting the SPA", { concurrency: false }, () => verifyLogoutRendersLogin({
  expectedLogin: "Staff Access",
  role: "staff",
}));
