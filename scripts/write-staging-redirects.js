import { mkdir, writeFile } from "node:fs/promises";

const rawOrigin = process.env.JDS_STAGING_API_ORIGIN || "";
const origin = new URL(rawOrigin);
if (
  origin.protocol !== "https:"
  || !origin.hostname.endsWith(".onrender.com")
  || origin.username
  || origin.password
  || origin.pathname !== "/"
  || origin.search
  || origin.hash
) {
  throw new Error("JDS_STAGING_API_ORIGIN must be an HTTPS onrender.com origin without a path.");
}

await mkdir("dist", { recursive: true });
await writeFile(
  "dist/_redirects",
  [
    `/api/*  ${origin.origin}/api/:splat  200`,
    `/health/*  ${origin.origin}/health/:splat  200`,
    `/robots.txt  ${origin.origin}/robots.txt  200`,
    "/*  /index.html  200",
    "",
  ].join("\n"),
  "utf8",
);
