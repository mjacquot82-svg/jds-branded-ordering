import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("staging surfaces render an unmistakable banner and fixture payment message", async () => {
  const layout = await readFile(new URL("../../src/layouts/AppLayout.jsx", import.meta.url), "utf8");
  const cart = await readFile(new URL("../../src/pages/CartPage.jsx", import.meta.url), "utf8");
  assert.match(layout, /STAGING|review\.label/);
  assert.match(layout, /the-guest-house/);
  assert.match(layout, /second-street-cafe/);
  assert.match(cart, /Real payments disabled in staging/);
});

test("staging Netlify config is noindex and same-origin proxies precede SPA fallback", async () => {
  const config = await readFile(new URL("../../netlify.staging.toml", import.meta.url), "utf8");
  const writer = await readFile(new URL("../../scripts/write-staging-redirects.js", import.meta.url), "utf8");
  assert.match(config, /X-Robots-Tag = "noindex, nofollow"/);
  assert.ok(writer.indexOf("/api/\*") < writer.indexOf("/\*  /index.html"));
  assert.ok(writer.indexOf("/health/\*") < writer.indexOf("/\*  /index.html"));
  assert.match(writer, /\.onrender\.com/);
  assert.doesNotMatch(writer, /VITE_/);
});
