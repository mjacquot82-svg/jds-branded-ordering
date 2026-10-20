import { mkdir, readFile, writeFile } from "node:fs/promises";

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
if (process.env.JDS_PILOT_SITE === "true") {
  await writeFile("dist/_headers", "/*\n  X-Robots-Tag: noindex, nofollow\n", "utf8");
  // The default build keeps Ladel's / Guest House page title, favicons
  // (their live app is unchanged; the install manifest is served per shop by the API). Pilot shops get neutral ones.
  const html = await readFile("dist/index.html", "utf8");
  await writeFile(
    "dist/index.html",
    html
      .replace(/<title>[^<]*<\/title>/, "<title>Order online</title>")
      .replace(/<link rel="(icon|shortcut icon|apple-touch-icon)"[^>]*>\s*/g, "")
      .replace("</head>", '    <link rel="icon" type="image/svg+xml" href="/jds-operations-icon.svg" />\n  </head>'),
    "utf8",
  );
}
