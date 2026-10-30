/**
 * Branded QR codes, generated in the browser (no paid services).
 * High error correction (H, ~30%) lets the shop logo cover the centre safely.
 */
import QRCode from "qrcode";

// Logo box covers at most this share of the QR width (≈ 4% of modules area, well under H's 30%).
export const LOGO_FRACTION = 0.2;
const QUIET_ZONE = 4;

export function buildQrMatrix(url) {
  const qr = QRCode.create(String(url), { errorCorrectionLevel: "H" });
  const size = qr.modules.size;
  const rows = [];
  for (let y = 0; y < size; y += 1) {
    const row = [];
    for (let x = 0; x < size; x += 1) row.push(Boolean(qr.modules.get(y, x)));
    rows.push(row);
  }
  return { size, rows };
}

function relativeLuminance(hex) {
  const value = String(hex || "").replace("#", "");
  if (!/^[0-9a-f]{6}$/i.test(value)) return 1;
  const channel = (index) => {
    const c = parseInt(value.slice(index, index + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
}

export function contrastRatio(a, b) {
  const [l1, l2] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

/** Dark brand colour for modules on a light background; falls back to near-black if contrast is weak. */
export function qrColors(colors = {}) {
  const light = "#ffffff";
  const candidates = [colors.text, colors.primary, colors.accent].filter(Boolean);
  const dark = candidates.find((value) => contrastRatio(value, light) >= 4.5) || "#1f2420";
  return { dark, light };
}

function logoBox(size) {
  const total = size + QUIET_ZONE * 2;
  const box = Math.max(3, Math.round(total * LOGO_FRACTION));
  const start = (total - box) / 2;
  return { total, box, start };
}

/** SVG string of the QR with optional centred logo (data URL). */
export function brandedQrSvg(url, { colors, logoDataUrl, pixelSize = 1024 } = {}) {
  const { size, rows } = buildQrMatrix(url);
  const { dark, light } = qrColors(colors);
  const { total, box, start } = logoBox(size);
  const path = [];
  rows.forEach((row, y) => row.forEach((on, x) => {
    if (on) path.push(`M${x + QUIET_ZONE} ${y + QUIET_ZONE}h1v1h-1z`);
  }));
  const pad = box * 0.08;
  const logo = logoDataUrl
    ? `<rect x="${start}" y="${start}" width="${box}" height="${box}" rx="${box * 0.18}" fill="${light}"/>` +
      `<image href="${logoDataUrl}" x="${start + pad}" y="${start + pad}" width="${box - pad * 2}" height="${box - pad * 2}" preserveAspectRatio="xMidYMid meet"/>`
    : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${total} ${total}" width="${pixelSize}" height="${pixelSize}" shape-rendering="crispEdges">` +
    `<rect width="${total}" height="${total}" fill="${light}"/><path fill="${dark}" d="${path.join("")}"/>${logo}</svg>`;
}

/**
 * Greyscale RGBA bitmap of the QR with the logo area blanked (worst case for scanning).
 * Used by tests to prove the branded code still decodes.
 */
export function qrBitmap(url, { scale = 8, withLogo = true } = {}) {
  const { size, rows } = buildQrMatrix(url);
  const { total, box, start } = logoBox(size);
  const width = total * scale;
  const data = new Uint8ClampedArray(width * width * 4).fill(255);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const mx = x + QUIET_ZONE; const my = y + QUIET_ZONE;
      const inLogo = withLogo && mx >= start && mx < start + box && my >= start && my < start + box;
      if (!rows[y][x] || inLogo) continue;
      for (let dy = 0; dy < scale; dy += 1) {
        for (let dx = 0; dx < scale; dx += 1) {
          const offset = ((my * scale + dy) * width + (mx * scale + dx)) * 4;
          data[offset] = 0; data[offset + 1] = 0; data[offset + 2] = 0;
        }
      }
    }
  }
  return { data, width, height: width };
}
