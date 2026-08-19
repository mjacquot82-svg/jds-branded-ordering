import assert from "node:assert/strict";
import { after, test } from "node:test";

import { JSDOM } from "jsdom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const vite = await createServer({ appType: "custom", server: { hmr: false, middlewareMode: true } });
const { default: NotificationSettings } = await vite.ssrLoadModule("/src/components/NotificationSettings.jsx");

after(() => vite.close());

const response = (status, payload = {}) => ({
  json: async () => payload,
  ok: status >= 200 && status < 300,
  status,
});

async function waitForText(container, text) {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (container.textContent.includes(text)) return;
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
  }
  assert.fail(`Expected notification settings to contain: ${text}\nActual: ${container.textContent}`);
}

async function notificationHarness({ saveStatus = 201 } = {}) {
  const dom = new JSDOM("<div id=\"root\"></div>", { url: "https://ladels.example/account" });
  const previous = {
    document: globalThis.document,
    fetch: globalThis.fetch,
    localStorage: globalThis.localStorage,
    navigator: globalThis.navigator,
    Notification: globalThis.Notification,
    window: globalThis.window,
  };
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.localStorage = dom.window.localStorage;
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
  Object.defineProperty(dom.window, "PushManager", { configurable: true, value: class PushManager {} });
  Object.defineProperty(dom.window.navigator, "platform", { configurable: true, value: "Android" });

  let currentSubscription = null;
  let enabled = false;
  let unsubscribeCount = 0;
  const requests = [];
  const subscription = {
    endpoint: "https://push.example/android-capability",
    toJSON: () => ({
      endpoint: "https://push.example/android-capability",
      expirationTime: null,
      keys: { p256dh: "p256dh-value", auth: "auth-value" },
      futureBrowserField: "ignored",
    }),
    unsubscribe: async () => { unsubscribeCount += 1; currentSubscription = null; return true; },
  };
  const registration = {
    pushManager: {
      getSubscription: async () => currentSubscription,
      subscribe: async () => { currentSubscription = subscription; return subscription; },
    },
  };
  Object.defineProperty(dom.window.navigator, "serviceWorker", { configurable: true, value: { ready: Promise.resolve(registration) } });
  globalThis.Notification = { permission: "granted", requestPermission: async () => "granted" };
  dom.window.Notification = globalThis.Notification;

  globalThis.fetch = async (url, options = {}) => {
    const path = new URL(String(url), dom.window.location.origin).pathname;
    requests.push({ options, path });
    if (path.endsWith("/config")) return response(200, { enrollment_enabled: true, vapid_public_key: "B" + "A".repeat(86) });
    if (path.endsWith("/status")) return response(200, { active_device_count: enabled ? 1 : 0, lunch_special_enabled: enabled });
    if (path.endsWith("/subscriptions") && options.method === "POST") {
      if (saveStatus !== 201) return response(saveStatus, { detail: [{ loc: ["body", "expirationTime"], type: "extra_forbidden" }] });
      return response(201, { id: "android-device" });
    }
    if (path.endsWith("/preferences") && options.method === "PUT") {
      enabled = true;
      return response(200, { lunch_special_enabled: true });
    }
    if (path.endsWith("/revoke-current")) return response(204);
    throw new Error(`Unexpected notification request: ${path}`);
  };

  const container = document.getElementById("root");
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(NotificationSettings, { csrfToken: "csrf" })));
  await waitForText(container, "Enable café notifications");
  return {
    container,
    dom,
    requests,
    root,
    subscription,
    unsubscribeCount: () => unsubscribeCount,
    async cleanup() {
      await act(async () => root.unmount());
      dom.window.close();
      globalThis.window = previous.window;
      globalThis.document = previous.document;
      globalThis.fetch = previous.fetch;
      globalThis.localStorage = previous.localStorage;
      globalThis.Notification = previous.Notification;
      Object.defineProperty(globalThis, "navigator", { configurable: true, value: previous.navigator });
    },
  };
}

test("Android enrollment excludes expirationTime and reaches enabled current-device state", { concurrency: false }, async () => {
  const app = await notificationHarness();
  try {
    const button = [...app.container.querySelectorAll("button")].find((item) => item.textContent.includes("Enable café notifications"));
    await act(async () => button.click());
    await waitForText(app.container, "Café notifications are on");
    assert.match(app.container.textContent, /This device is enabled · 1 active device/);
    const request = app.requests.find(({ options, path }) => path.endsWith("/subscriptions") && options.method === "POST");
    const payload = JSON.parse(request.options.body);
    assert.deepEqual(payload, {
      endpoint: "https://push.example/android-capability",
      keys: { p256dh: "p256dh-value", auth: "auth-value" },
      content_encoding: "aes128gcm",
      device_label: "Android",
    });
    assert.equal(app.unsubscribeCount(), 0);
  } finally {
    await app.cleanup();
  }
});

test("backend enrollment rejection rolls back the new browser subscription", { concurrency: false }, async () => {
  const app = await notificationHarness({ saveStatus: 422 });
  try {
    const button = [...app.container.querySelectorAll("button")].find((item) => item.textContent.includes("Enable café notifications"));
    await act(async () => button.click());
    await waitForText(app.container, "Notification details were rejected. Please try again.");
    assert.equal(app.unsubscribeCount(), 1);
    assert.equal(app.requests.some(({ path }) => path.endsWith("/preferences")), false);
    assert.equal(app.requests.some(({ path }) => path.endsWith("/revoke-current")), false);
  } finally {
    await app.cleanup();
  }
});
