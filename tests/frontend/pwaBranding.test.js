import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../../", import.meta.url);
const manifest = JSON.parse(await readFile(new URL("public/manifest.webmanifest", root), "utf8"));
const index = await readFile(new URL("index.html", root), "utf8");

test("manifest exposes the Ladel's install identity and valid brand colors", () => {
  assert.equal(manifest.name, "Ladel's Wellness Café");
  assert.equal(manifest.short_name, "Ladel's");
  assert.doesNotMatch(JSON.stringify(manifest), /The Guest House|Guest House/);
  assert.match(manifest.background_color, /^#[0-9a-f]{6}$/i);
  assert.match(manifest.theme_color, /^#[0-9a-f]{6}$/i);
});

test("manifest uses distinct normal and maskable source assets", async () => {
  assert.deepEqual(
    manifest.icons.map(({ src, sizes, type, purpose }) => ({ src, sizes, type, purpose })),
    [
      { src: "/icon-192.png?v=ladel-master-1", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png?v=ladel-master-1", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-maskable-192.png?v=ladel-master-1", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icon-maskable-512.png?v=ladel-master-1", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  );
  assert.equal(new Set(manifest.icons.map(({ src }) => src)).size, manifest.icons.length);
  for (const { src } of manifest.icons) {
    assert.equal(src.startsWith("/dist/"), false);
    await access(new URL(`public${new URL(src, "https://example.test").pathname}`, root));
  }
});

test("browser and Apple metadata use the new source-controlled branding", async () => {
  assert.match(index, /<link rel="icon" type="image\/png" sizes="32x32" href="\/favicon-32x32\.png\?v=ladel-favicon-1" \/>/);
  assert.match(index, /<link rel="icon" type="image\/png" sizes="16x16" href="\/favicon-16x16\.png\?v=ladel-favicon-1" \/>/);
  assert.match(index, /<link rel="shortcut icon" href="\/favicon\.ico\?v=ladel-favicon-1" \/>/);
  assert.match(index, /<link rel="apple-touch-icon" sizes="180x180" href="\/apple-touch-icon\.png\?v=ladel-master-1" \/>/);
  assert.match(index, /<meta name="theme-color" content="#4c3426" \/>/);
  assert.match(index, /<title>Ladel's Wellness Café<\/title>/);
  assert.doesNotMatch(index, /The Guest House|Café &amp; Pantry/);
  await access(new URL("public/favicon-32x32.png", root));
  await access(new URL("public/favicon-16x16.png", root));
  await access(new URL("public/favicon.ico", root));
  await access(new URL("public/apple-touch-icon.png", root));
});

test("branding remains manifest-generated with no standalone or in-app splash", async () => {
  await assert.rejects(access(new URL("public/splash.png", root)));
  const app = await readFile(new URL("src/App.jsx", root), "utf8");
  assert.doesNotMatch(app, /Splash(?:Screen|Page|Component)|splash\.png/i);
});
