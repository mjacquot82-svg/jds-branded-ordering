import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { createPilotServer, safePathname, validateApiOrigin } from "../../scripts/canner-pilot-server.mjs";

function listen(server) {
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server.address().port)));
}

function request(port, { method = "GET", path: target = "/", headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: "127.0.0.1", port, method, path: target, headers }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks) }));
    });
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

async function setup() {
  const dist = await mkdtemp(path.join(os.tmpdir(), "canner-pilot-dist-"));
  await mkdir(path.join(dist, "assets"));
  await writeFile(path.join(dist, "index.html"), "<!doctype html><title>pilot</title>");
  await writeFile(path.join(dist, "assets", "app.js"), "console.log('app');");
  await writeFile(path.join(dist, "service-worker.js"), "self.addEventListener('fetch',()=>{});");
  await writeFile(path.join(path.dirname(dist), "canner-secret-outside-dist.txt"), "SECRET");
  const seen = [];
  const upstream = http.createServer((req, res) => {
    const hash = createHash("sha256");
    let length = 0;
    req.on("data", (chunk) => { hash.update(chunk); length += chunk.length; });
    req.on("end", () => {
      seen.push({ method: req.method, url: req.url, headers: req.headers, length, sha256: hash.digest("hex") });
      res.setHeader("Set-Cookie", [
        "__Host-jds_owner_session=abc; Path=/; Secure; HttpOnly; SameSite=Lax",
        "jds_other=1; Path=/; Secure; SameSite=Lax",
      ]);
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ ok: true }));
    });
  });
  const upstreamPort = await listen(upstream);
  const server = createPilotServer({ distDir: dist, apiOrigin: `http://127.0.0.1:${upstreamPort}`, allowInsecureLoopbackForTests: true });
  const port = await listen(server);
  return {
    port, seen,
    async close() {
      server.close(); upstream.close();
      await rm(dist, { recursive: true, force: true });
      await rm(path.join(path.dirname(dist), "canner-secret-outside-dist.txt"), { force: true });
    },
  };
}

test("startup refuses non-HTTPS, non-allowlisted, or non-bare API origins", () => {
  for (const bad of [
    "", "not a url", "http://jds-pilot-api.canner.app", "https://evil.example.com",
    "https://jds-pilot-api.canner.app.evil.com", "https://a.b.canner.app", "https://canner.app",
    "https://user:pw@jds-pilot-api.canner.app", "https://jds-pilot-api.canner.app/api",
    "https://jds-pilot-api.canner.app/?x=1", "http://127.0.0.1:8000",
  ]) {
    assert.throws(() => validateApiOrigin(bad), Error, bad);
  }
  assert.throws(() => createPilotServer({ distDir: ".", apiOrigin: "https://evil.example.com" }));
  assert.equal(validateApiOrigin("https://jds-pilot-api.canner.app").host, "jds-pilot-api.canner.app");
  assert.equal(validateApiOrigin("https://api.pilot.example.ca", { allowedHost: "api.pilot.example.ca" }).host, "api.pilot.example.ca");
  assert.throws(() => validateApiOrigin("https://other.example.ca", { allowedHost: "api.pilot.example.ca" }));
});

test("safePathname rejects traversal and protocol-relative targets", () => {
  for (const bad of ["/../etc/passwd", "/assets/%2e%2e/%2e%2e/x", "//evil.com/api/x", "/%2f%2fevil.com", "/a\\b", "/x%00", "/api/v1/../../x", "http://evil.com/api/x", "/%zz"]) {
    assert.equal(safePathname(bad), null, bad);
  }
  assert.equal(safePathname("/api/v1/owner/session?x=1"), "/api/v1/owner/session");
});

test("proxy preserves Origin, Cookie, CSRF header, multiple Set-Cookie and sets forwarded headers", async (t) => {
  const ctx = await setup();
  t.after(() => ctx.close());
  const res = await request(ctx.port, {
    method: "PUT", path: "/api/v1/owner/design?tab=a",
    headers: {
      Host: "jds-pilot-web.canner.app", Origin: "https://jds-pilot-web.canner.app",
      Cookie: "__Host-jds_owner_session=abc; other=2", "X-CSRF-Token": "tok-123",
      "Content-Type": "application/json", "X-Forwarded-Proto": "https", "X-Forwarded-Host": "spoofed.example",
    },
    body: JSON.stringify({ name: "Harbor" }),
  });
  assert.equal(res.status, 200);
  assert.deepEqual(res.headers["set-cookie"], [
    "__Host-jds_owner_session=abc; Path=/; Secure; HttpOnly; SameSite=Lax",
    "jds_other=1; Path=/; Secure; SameSite=Lax",
  ]);
  assert.equal(res.headers["x-robots-tag"], "noindex, nofollow");
  const forwarded = ctx.seen.at(-1);
  assert.equal(forwarded.method, "PUT");
  assert.equal(forwarded.url, "/api/v1/owner/design?tab=a");
  assert.equal(forwarded.headers.origin, "https://jds-pilot-web.canner.app");
  assert.equal(forwarded.headers.cookie, "__Host-jds_owner_session=abc; other=2");
  assert.equal(forwarded.headers["x-csrf-token"], "tok-123");
  assert.equal(forwarded.headers["x-forwarded-host"], "jds-pilot-web.canner.app");
  assert.equal(forwarded.headers["x-forwarded-proto"], "https");
  assert.match(forwarded.headers.host, /^127\.0\.0\.1:\d+$/);
});

test("health paths are proxied; only /api/ and /health/ prefixes leave the server", async (t) => {
  const ctx = await setup();
  t.after(() => ctx.close());
  assert.equal((await request(ctx.port, { path: "/health/ready" })).status, 200);
  assert.equal(ctx.seen.at(-1).url, "/health/ready");
  const before = ctx.seen.length;
  for (const target of ["/apix", "/api", "/admin", "/healthz", "/docs"]) await request(ctx.port, { path: target });
  assert.equal(ctx.seen.length, before);
});

test("upload bodies over 10 MB stream through unchanged", async (t) => {
  const ctx = await setup();
  t.after(() => ctx.close());
  const body = randomBytes(11 * 1024 * 1024);
  const res = await request(ctx.port, {
    method: "POST", path: "/api/v1/platform/media", body,
    headers: { "Content-Type": "image/jpeg", "Content-Length": body.length },
  });
  assert.equal(res.status, 200);
  assert.equal(ctx.seen.at(-1).length, body.length);
  assert.equal(ctx.seen.at(-1).sha256, createHash("sha256").update(body).digest("hex"));
});

test("traversal requests are refused and never read files outside dist", async (t) => {
  const ctx = await setup();
  t.after(() => ctx.close());
  for (const target of ["/../canner-secret-outside-dist.txt", "/%2e%2e/canner-secret-outside-dist.txt", "/assets/..%2f..%2fcanner-secret-outside-dist.txt", "//evil.com/api/x", "/api/v1/%2e%2e/%2e%2e/admin"]) {
    const res = await request(ctx.port, { path: target });
    assert.equal(res.status, 400, target);
    assert.ok(!res.body.toString().includes("SECRET"));
  }
  assert.equal(ctx.seen.length, 0);
});

test("static files, SPA fallback, noindex header, robots and service worker headers", async (t) => {
  const ctx = await setup();
  t.after(() => ctx.close());
  const root = await request(ctx.port, { path: "/" });
  assert.equal(root.status, 200);
  assert.match(root.body.toString(), /pilot/);
  assert.equal(root.headers["x-robots-tag"], "noindex, nofollow");
  const deep = await request(ctx.port, { path: "/build/verify?token=x" });
  assert.equal(deep.status, 200);
  assert.match(deep.headers["content-type"], /text\/html/);
  assert.equal(deep.headers["x-robots-tag"], "noindex, nofollow");
  const asset = await request(ctx.port, { path: "/assets/app.js" });
  assert.match(asset.headers["cache-control"], /immutable/);
  assert.equal((await request(ctx.port, { path: "/assets/missing.js" })).status, 404);
  const robots = await request(ctx.port, { path: "/robots.txt" });
  assert.equal(robots.body.toString(), "User-agent: *\nDisallow: /\n");
  const sw = await request(ctx.port, { path: "/service-worker.js" });
  assert.equal(sw.headers["service-worker-allowed"], "/");
  assert.match(sw.headers["cache-control"], /no-store/);
  assert.equal((await request(ctx.port, { method: "POST", path: "/build" })).status, 405);
});
