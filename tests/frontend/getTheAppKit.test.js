import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import jsQR from "jsqr";

import { brandedQrSvg, buildQrMatrix, contrastRatio, qrBitmap, qrColors } from "../../src/marketing/brandedQr.js";
import { HEADLINE, HOW_TO, KIT_DESIGNS, escapeXml } from "../../src/marketing/kitDesigns.js";
import { shareApp } from "../../src/marketing/shareApp.js";
import { installMode, isIos, isStandalone } from "../../src/services/installPrompt.js";

const read = (path) => readFile(new URL(`../../${path}`, import.meta.url), "utf8");
const SHOP_URL = "https://test-bean-cafe.jdsstudio.ca/";

test("branded QR uses high error correction and still decodes to the shop URL with the logo area covered", () => {
  for (const url of [SHOP_URL, "https://a-much-longer-shop-name-example.jdsstudio.ca/?review_tenant=second-street-cafe"]) {
    const bitmap = qrBitmap(url, { withLogo: true });
    const decoded = jsQR(bitmap.data, bitmap.width, bitmap.height);
    assert.equal(decoded?.data, url);
  }
  const matrix = buildQrMatrix(SHOP_URL);
  assert.ok(matrix.size >= 21);
});

test("QR colours keep strong contrast, falling back to near-black for pale brands", () => {
  assert.ok(contrastRatio(qrColors({ text: "#2f3328" }).dark, "#ffffff") >= 4.5);
  assert.equal(qrColors({ text: "#f0f0f0", primary: "#eeeeee", accent: "#dddddd" }).dark, "#1f2420");
});

test("QR SVG embeds the logo in a centred white box", () => {
  const svg = brandedQrSvg(SHOP_URL, { colors: { text: "#2f3328" }, logoDataUrl: "data:image/png;base64,AAAA" });
  assert.match(svg, /<image href="data:image\/png;base64,AAAA"/);
  assert.match(svg, /fill="#2f3328"/);
});

test("every kit design says 'Scan to get our app' with the how-to, shop name and URL, escaped", () => {
  const shop = { url: SHOP_URL, name: "Bean & <Co>", colors: { primary: "#6f7d5f", accent: "#b98564", background: "#f7f0e6", text: "#2f3328" }, logoDataUrl: null };
  assert.deepEqual(KIT_DESIGNS.map((d) => d.key), ["qr", "counter-sign", "table-tent", "window-sticker", "social-post"]);
  for (const design of KIT_DESIGNS.filter((d) => d.key !== "qr")) {
    const svg = design.build(shop);
    assert.ok(svg.includes(escapeXml(HEADLINE)), design.key);
    assert.ok(svg.includes(escapeXml(HOW_TO)), design.key);
    assert.ok(svg.includes("Bean &amp; &lt;Co&gt;"), design.key);
    assert.ok(!svg.includes("<Co>"), design.key);
  }
});

test("install mode: hidden when installed, prompt on Android, help on iPhone", () => {
  assert.equal(installMode({ standalone: true, ios: true, hasPrompt: true }), "hidden");
  assert.equal(installMode({ standalone: false, ios: false, hasPrompt: true }), "prompt");
  assert.equal(installMode({ standalone: false, ios: true, hasPrompt: false }), "ios");
  assert.equal(installMode({ standalone: false, ios: false, hasPrompt: false }), "hidden");
  assert.equal(isIos({ userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)" }), true);
  assert.equal(isIos({ userAgent: "Mozilla/5.0 (Macintosh)", platform: "MacIntel", maxTouchPoints: 5 }), true);
  assert.equal(isIos({ userAgent: "Mozilla/5.0 (Linux; Android 15)" }), false);
  assert.equal(isStandalone({ matchMedia: () => ({ matches: true }) }), true);
  assert.equal(isStandalone({ matchMedia: () => ({ matches: false }), navigator: { standalone: true } }), true);
  assert.equal(isStandalone({ matchMedia: () => ({ matches: false }), navigator: {} }), false);
});

test("share uses the share sheet, else copies the link", async () => {
  let shared;
  assert.equal(await shareApp({ url: SHOP_URL, name: "Test Bean Café" }, { nav: { share: async (d) => { shared = d; } } }), "shared");
  assert.equal(shared.url, SHOP_URL);
  let copied;
  assert.equal(await shareApp({ url: SHOP_URL, name: "X" }, { nav: { clipboard: { writeText: async (v) => { copied = v; } } } }), "copied");
  assert.equal(copied, SHOP_URL);
  const abort = Object.assign(new Error("x"), { name: "AbortError" });
  assert.equal(await shareApp({ url: SHOP_URL, name: "X" }, { nav: { share: async () => { throw abort; } } }), "cancelled");
});

test("Get the app is wired into the customer layout and Marketing kit into Launch", async () => {
  const layout = await read("src/layouts/AppLayout.jsx");
  assert.match(layout, /showCustomerFooter \? <GetAppButton/);
  const main = await read("src/main.jsx");
  assert.match(main, /captureInstallPrompt\(window\)/);
  const button = await read("src/components/GetAppButton.jsx");
  assert.match(button, /Add to Home Screen/);
  assert.match(button, /if \(mode === "hidden"\) return null/);
  const launch = await read("src/admin/LaunchPage.jsx");
  assert.match(launch, /<MarketingKit kit=\{kit\} slug=\{storefront\.slug\}\/>/);
  assert.match(launch, /scan and get your app/);
});
