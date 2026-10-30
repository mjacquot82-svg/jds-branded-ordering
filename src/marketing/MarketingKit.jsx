import { useEffect, useMemo, useState } from "react";
import { KIT_DESIGNS } from "./kitDesigns.js";
import { shareApp } from "./shareApp.js";

const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || "";

async function toDataUrl(path) {
  if (!path) return null;
  try {
    const response = await fetch(`${API_BASE_URL.replace(/\/+$/, "")}${path}`, { credentials: "include" });
    if (!response.ok) return null;
    const blob = await response.blob();
    return await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
}

function svgDataUrl(svg) {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function download(href, filename) {
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

/** Draw the SVG on a canvas and save a PNG. All in the browser; logo is an embedded data URL. */
async function downloadPng(svg, filename) {
  const image = new Image();
  const loaded = new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; });
  image.src = svgDataUrl(svg);
  await loaded;
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth || image.width;
  canvas.height = image.naturalHeight || image.height;
  canvas.getContext("2d").drawImage(image, 0, 0);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  const href = URL.createObjectURL(blob);
  download(href, filename);
  setTimeout(() => URL.revokeObjectURL(href), 5000);
}

function printSvg(svg, title) {
  const win = window.open("", "_blank");
  if (!win) return;
  win.document.write(`<!doctype html><title>${title}</title><style>@page{margin:0}body{margin:0;display:grid;place-items:center}img{max-width:100%;max-height:100vh}</style><img src="${svgDataUrl(svg)}" onload="print()">`);
  win.document.close();
}

export default function MarketingKit({ kit, slug }) {
  const [logoDataUrl, setLogoDataUrl] = useState(null);
  const [shareStatus, setShareStatus] = useState("");
  useEffect(() => { let active = true; toDataUrl(kit.logoUrl).then((value) => { if (active) setLogoDataUrl(value); }); return () => { active = false; }; }, [kit.logoUrl]);
  const shop = useMemo(() => ({ url: kit.url, name: kit.name || slug, colors: kit.colors || {}, logoDataUrl }), [kit, slug, logoDataUrl]);
  const designs = useMemo(() => KIT_DESIGNS.map((design) => ({ ...design, svg: design.build(shop) })), [shop]);

  async function handleShare() {
    const result = await shareApp({ url: kit.url, name: shop.name });
    setShareStatus(result === "copied" ? "Link copied — paste it in a text, email, or post." : result === "shared" ? "Shared." : result === "failed" ? "Couldn’t share. Copy the link above instead." : "");
  }

  return <section className="operations-panel marketing-kit" aria-labelledby="marketing-kit-title">
    <h2 id="marketing-kit-title">Marketing kit</h2>
    <p>Help customers get your app. Everything below uses your logo and colours and points to your app.</p>
    <div className="design-actions">
      <button className="primary-button" type="button" onClick={handleShare}>Share your app</button>
    </div>
    {shareStatus ? <p role="status">{shareStatus}</p> : null}
    <div className="marketing-kit-grid">
      {designs.map((design) => <article className="marketing-kit-item" key={design.key}>
        <img src={svgDataUrl(design.svg)} alt={`${design.title} for ${shop.name}`} loading="lazy" />
        <h3>{design.title}</h3>
        <p>{design.note}</p>
        <div className="design-actions">
          <button className="secondary-button" type="button" onClick={() => downloadPng(design.svg, `${slug}-${design.key}.png`)}>Download PNG</button>
          <button className="secondary-button" type="button" onClick={() => download(svgDataUrl(design.svg), `${slug}-${design.key}.svg`)}>Download SVG</button>
          {design.key !== "social-post" && design.key !== "qr" ? <button className="secondary-button" type="button" onClick={() => printSvg(design.svg, design.title)}>Print</button> : null}
        </div>
      </article>)}
    </div>
  </section>;
}
