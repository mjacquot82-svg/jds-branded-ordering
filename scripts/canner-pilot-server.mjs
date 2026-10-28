// Controlled DEMO PILOT web server for Canner (https://canner.ca).
// Serves the built Vite app from dist/ and forwards the same paths the
// Netlify pilot proxies (/api/*, /health/*) to the pilot API project, so the
// browser sees one origin and the __Host- session cookie + CSRF header work.
// Node built-ins only. Not used by Guest House / Ladel's / Netlify builds.
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import http from "node:http";
import https from "node:https";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const PROXY_PREFIXES = ["/api/", "/health/"];
const HOP_BY_HOP = new Set([
  "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "proxy-connection",
  "te", "trailer", "transfer-encoding", "upgrade", "host", "forwarded",
  "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-real-ip",
]);
const NOINDEX = "noindex, nofollow";
const ROBOTS_BODY = "User-agent: *\nDisallow: /\n";
const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".webmanifest": "application/manifest+json",
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".webp": "image/webp", ".ico": "image/x-icon", ".gif": "image/gif", ".txt": "text/plain; charset=utf-8",
  ".woff": "font/woff", ".woff2": "font/woff2", ".map": "application/json; charset=utf-8",
};

/** Validate the upstream API origin. Throws on anything but a bare HTTPS origin on an allowed host. */
export function validateApiOrigin(rawOrigin, { allowedHost = "", allowInsecureLoopbackForTests = false } = {}) {
  let origin;
  try {
    origin = new URL(rawOrigin || "");
  } catch {
    throw new Error("PILOT_API_ORIGIN must be an absolute URL.");
  }
  const host = origin.hostname.toLowerCase();
  const loopback = allowInsecureLoopbackForTests && origin.protocol === "http:" && (host === "127.0.0.1" || host === "localhost");
  if (!loopback && origin.protocol !== "https:") throw new Error("PILOT_API_ORIGIN must use HTTPS.");
  if (origin.username || origin.password || origin.pathname !== "/" || origin.search || origin.hash) {
    throw new Error("PILOT_API_ORIGIN must be a bare origin without credentials, path, query, or fragment.");
  }
  const explicit = (allowedHost || "").trim().toLowerCase();
  const cannerHost = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.canner\.app$/.test(host);
  if (!loopback && !cannerHost && !(explicit && host === explicit)) {
    throw new Error("PILOT_API_ORIGIN host must be a single-label *.canner.app host or equal PILOT_API_ALLOWED_HOST.");
  }
  return origin;
}

function securityHeaders(extra = {}) {
  return { "X-Robots-Tag": NOINDEX, "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin", ...extra };
}

function send(res, status, body, headers = {}) {
  res.writeHead(status, securityHeaders({ "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", ...headers }));
  res.end(body);
}

/** Return the decoded pathname, or null when the request target is unsafe. */
export function safePathname(rawUrl) {
  if (typeof rawUrl !== "string" || !rawUrl.startsWith("/") || rawUrl.startsWith("//")) return null;
  const rawPath = rawUrl.split("?", 1)[0];
  if (rawPath.includes("\\")) return null;
  let decoded;
  try {
    decoded = decodeURIComponent(rawPath);
  } catch {
    return null;
  }
  if (decoded.includes("\0") || decoded.includes("\\") || decoded.startsWith("//")) return null;
  if (decoded.split("/").some((segment) => segment === ".." || segment === ".")) return null;
  return decoded;
}

function proxy(req, res, upstream, rawUrl, transport) {
  const target = new URL(upstream.origin + rawUrl);
  if (target.origin !== upstream.origin) return send(res, 400, "Bad request.\n");
  const headers = {};
  for (const [name, value] of Object.entries(req.headers)) {
    if (!HOP_BY_HOP.has(name.toLowerCase())) headers[name] = value;
  }
  headers.host = target.host;
  const incomingHost = String(req.headers.host || "").split(",", 1)[0].trim();
  const incomingProto = String(req.headers["x-forwarded-proto"] || "").split(",", 1)[0].trim().toLowerCase();
  headers["x-forwarded-host"] = incomingHost;
  headers["x-forwarded-proto"] = incomingProto === "http" ? "http" : "https";
  if (req.socket.remoteAddress) headers["x-forwarded-for"] = req.socket.remoteAddress;

  const upstreamReq = transport.request(target, { method: req.method, headers }, (upstreamRes) => {
    const responseHeaders = {};
    for (const [name, value] of Object.entries(upstreamRes.headers)) {
      if (!HOP_BY_HOP.has(name.toLowerCase())) responseHeaders[name] = value; // set-cookie stays an array
    }
    responseHeaders["x-robots-tag"] = NOINDEX;
    res.writeHead(upstreamRes.statusCode || 502, responseHeaders);
    upstreamRes.pipe(res);
  });
  upstreamReq.setTimeout(120_000, () => upstreamReq.destroy(new Error("upstream timeout")));
  upstreamReq.on("error", () => {
    if (!res.headersSent) send(res, 502, "The pilot API is unavailable.\n");
    else res.destroy();
  });
  req.on("aborted", () => upstreamReq.destroy());
  req.pipe(upstreamReq);
}

async function serveFile(res, method, filePath, pathname) {
  const ext = path.extname(filePath).toLowerCase();
  const info = await stat(filePath);
  let cache = "public, max-age=300";
  if (pathname.startsWith("/assets/")) cache = "public, max-age=31536000, immutable";
  if (ext === ".html") cache = "no-cache";
  const extra = { "Content-Type": MIME[ext] || "application/octet-stream", "Content-Length": info.size, "Cache-Control": cache };
  if (pathname === "/service-worker.js") {
    Object.assign(extra, { "Cache-Control": "no-cache, no-store, must-revalidate", "Content-Type": "application/javascript; charset=utf-8", "Service-Worker-Allowed": "/" });
  }
  res.writeHead(200, securityHeaders(extra));
  if (method === "HEAD") return res.end();
  createReadStream(filePath).pipe(res);
}

async function resolveStatic(distRoot, pathname) {
  const candidate = path.resolve(distRoot, "." + pathname);
  if (candidate !== distRoot && !candidate.startsWith(distRoot + path.sep)) return null;
  try {
    const info = await stat(candidate);
    if (info.isFile()) return candidate;
    if (info.isDirectory()) {
      const index = path.join(candidate, "index.html");
      if ((await stat(index)).isFile()) return index;
    }
  } catch {
    // fall through to SPA fallback
  }
  return null;
}

export function createPilotServer({ distDir, apiOrigin, allowedHost = "", allowInsecureLoopbackForTests = false }) {
  const upstream = validateApiOrigin(apiOrigin, { allowedHost, allowInsecureLoopbackForTests });
  const transport = upstream.protocol === "https:" ? https : http;
  const distRoot = path.resolve(distDir);
  const indexFile = path.join(distRoot, "index.html");

  return http.createServer(async (req, res) => {
    try {
      const rawUrl = req.url || "/";
      const pathname = safePathname(rawUrl);
      if (pathname === null) return send(res, 400, "Bad request.\n");
      if (PROXY_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
        return proxy(req, res, upstream, rawUrl, transport);
      }
      if (req.method !== "GET" && req.method !== "HEAD") return send(res, 405, "Method not allowed.\n", { Allow: "GET, HEAD" });
      if (pathname === "/robots.txt") return send(res, 200, req.method === "HEAD" ? "" : ROBOTS_BODY, { "Cache-Control": "public, max-age=300" });
      const file = await resolveStatic(distRoot, pathname);
      if (file) return await serveFile(res, req.method, file, pathname);
      if (path.extname(pathname) && pathname.startsWith("/assets/")) return send(res, 404, "Not found.\n");
      return await serveFile(res, req.method, indexFile, "/index.html");
    } catch {
      if (!res.headersSent) send(res, 500, "Server error.\n");
      else res.destroy();
    }
  });
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
if (isMain) {
  const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const server = createPilotServer({
    distDir: process.env.PILOT_DIST_DIR || path.join(repoRoot, "dist"),
    apiOrigin: process.env.PILOT_API_ORIGIN,
    allowedHost: process.env.PILOT_API_ALLOWED_HOST || "",
  });
  server.requestTimeout = 0; // allow slow 10 MB uploads; upstream timeout still applies
  const port = Number(process.env.PORT || 3000);
  server.listen(port, "0.0.0.0", () => {
    console.log(`canner pilot web listening on ${port}, proxying /api/* and /health/* to ${new URL(process.env.PILOT_API_ORIGIN).origin}`);
  });
}
