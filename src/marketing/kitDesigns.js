/** Printable marketing kit designs as SVG strings, in the shop's own branding. */
import { brandedQrSvg } from "./brandedQr.js";

export const HEADLINE = "Scan to get our app";
export const HOW_TO = "Point your phone camera at the code, then tap “Get the app”.";

const FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

export function escapeXml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" })[c]);
}

function placedQr(url, { colors, logoDataUrl }, x, y, size) {
  const svg = brandedQrSvg(url, { colors, logoDataUrl, pixelSize: size });
  return svg.replace(/^<svg /, `<svg x="${x}" y="${y}" `);
}

function shortUrl(url) {
  return String(url || "").replace(/^https?:\/\//, "").replace(/\/$/, "");
}

function text(x, y, size, fill, value, { weight = 700, anchor = "middle", maxWidth = x * 1.7 } = {}) {
  // Long names/URLs shrink to fit instead of running off the design.
  const estimated = String(value ?? "").length * size * 0.56;
  const fitted = estimated > maxWidth ? Math.max(12, Math.floor(size * maxWidth / estimated)) : size;
  return `<text x="${x}" y="${y}" font-family="${FONT}" font-size="${fitted}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}">${escapeXml(value)}</text>`;
}

function logoMark(logoDataUrl, cx, cy, size) {
  if (!logoDataUrl) return "";
  return `<image href="${logoDataUrl}" x="${cx - size / 2}" y="${cy - size / 2}" width="${size}" height="${size}" preserveAspectRatio="xMidYMid meet"/>`;
}

function wrap(width, height, body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">${body}</svg>`;
}

/** One portrait panel: logo, name, headline, QR card, how-to, URL. */
function panel(shop, width, height, scale = 1) {
  const c = shop.colors || {};
  const cx = width / 2;
  const qrSize = Math.round(width * 0.62);
  const qrY = Math.round(height * 0.33);
  const card = 36 * scale;
  return [
    `<rect width="${width}" height="${height}" fill="${c.primary || "#6f7d5f"}"/>`,
    `<rect x="${width * 0.06}" y="${width * 0.06}" width="${width * 0.88}" height="${height - width * 0.12}" rx="${48 * scale}" fill="${c.background || "#f7f0e6"}"/>`,
    logoMark(shop.logoDataUrl, cx, height * 0.1, 150 * scale),
    text(cx, height * 0.19, 64 * scale, c.text || "#2f3328", shop.name),
    text(cx, height * 0.27, 96 * scale, c.primary || "#6f7d5f", HEADLINE, { weight: 800 }),
    `<rect x="${cx - qrSize / 2 - card}" y="${qrY - card}" width="${qrSize + card * 2}" height="${qrSize + card * 2}" rx="${32 * scale}" fill="#ffffff" stroke="${c.accent || "#b98564"}" stroke-width="${8 * scale}"/>`,
    placedQr(shop.url, shop, cx - qrSize / 2, qrY, qrSize),
    text(cx, qrY + qrSize + card + 90 * scale, 40 * scale, c.text || "#2f3328", HOW_TO, { weight: 500 }),
    text(cx, qrY + qrSize + card + 160 * scale, 40 * scale, c.accent || "#b98564", shortUrl(shop.url), { weight: 700 }),
  ].join("");
}

export function counterSignSvg(shop) {
  return wrap(1500, 2100, panel(shop, 1500, 2100));
}

/** Fold along the middle line; the top panel is upside down so both sides read correctly. */
export function tableTentSvg(shop) {
  const w = 1200; const h = 1800;
  return wrap(w, h * 2, `<g transform="rotate(180 ${w / 2} ${h / 2})">${panel(shop, w, h, 0.8)}</g>` +
    `<g transform="translate(0 ${h})">${panel(shop, w, h, 0.8)}</g>` +
    `<line x1="0" y1="${h}" x2="${w}" y2="${h}" stroke="#999" stroke-width="3" stroke-dasharray="18 14"/>`);
}

export function windowStickerSvg(shop) {
  const s = 1500; const c = shop.colors || {}; const qr = 720;
  return wrap(s, s, [
    `<circle cx="${s / 2}" cy="${s / 2}" r="${s / 2 - 6}" fill="${c.primary || "#6f7d5f"}"/>`,
    `<circle cx="${s / 2}" cy="${s / 2}" r="${s / 2 - 70}" fill="${c.background || "#f7f0e6"}"/>`,
    text(s / 2, 300, 92, c.primary || "#6f7d5f", HEADLINE, { weight: 800 }),
    text(s / 2, 395, 60, c.text || "#2f3328", shop.name),
    `<rect x="${(s - qr) / 2 - 30}" y="440" width="${qr + 60}" height="${qr + 60}" rx="30" fill="#ffffff"/>`,
    placedQr(shop.url, shop, (s - qr) / 2, 470, qr),
    text(s / 2, 1290, 40, c.text || "#2f3328", HOW_TO, { weight: 500, maxWidth: 900 }),
  ].join(""));
}

export function socialPostSvg(shop) {
  const s = 1080; const c = shop.colors || {}; const qr = 520;
  return wrap(s, s, [
    `<rect width="${s}" height="${s}" fill="${c.primary || "#6f7d5f"}"/>`,
    text(s / 2, 150, 72, "#ffffff", shop.name),
    text(s / 2, 260, 84, "#ffffff", HEADLINE, { weight: 800 }),
    `<rect x="${(s - qr) / 2 - 28}" y="312" width="${qr + 56}" height="${qr + 56}" rx="28" fill="#ffffff"/>`,
    placedQr(shop.url, shop, (s - qr) / 2, 340, qr),
    text(s / 2, 960, 34, "#ffffff", HOW_TO, { weight: 500 }),
    text(s / 2, 1020, 36, c.background || "#f7f0e6", shortUrl(shop.url)),
  ].join(""));
}

export const KIT_DESIGNS = [
  { key: "qr", title: "QR code", note: "Your logo in the middle, your colours.", build: (shop) => brandedQrSvg(shop.url, { colors: shop.colors, logoDataUrl: shop.logoDataUrl, pixelSize: 1200 }) },
  { key: "counter-sign", title: "Counter sign", note: "5 × 7 in, portrait.", build: counterSignSvg },
  { key: "table-tent", title: "Table tent", note: "4 × 6 in each side. Print, fold on the dotted line.", build: tableTentSvg },
  { key: "window-sticker", title: "Window sticker", note: "Round, 10 in.", build: windowStickerSvg },
  { key: "social-post", title: "Social post", note: "Square, for Instagram or Facebook.", build: socialPostSvg },
];
