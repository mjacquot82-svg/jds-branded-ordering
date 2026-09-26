// Neutral JDS branding for operations routes (owner/admin tools, setup, /build).
// Customer storefront pages keep their tenant branding; these routes never show a
// café's name or icon (e.g. "Ladel's Wellness Café" from index.html) as the page identity.
export const OPERATIONS_PATH = /^\/(admin|owner|staff|build|activate|setup|go-live)(\/|$)/;
export const JDS_OPERATIONS_NAME = "JDS Branded Ordering";
export const JDS_OPERATIONS_ICON = "/jds-operations-icon.svg";
export const JDS_OPERATIONS_THEME = "#26312a";
const TENANT_VARIABLES = ["--tenant-primary", "--tenant-accent", "--tenant-background", "--tenant-surface", "--tenant-text"];

export function isOperationsPath(pathname = "") {
  return OPERATIONS_PATH.test(pathname || "");
}

export function operationsTitle(pathname = "") {
  if (/^\/build(\/|$)/.test(pathname)) return `Build your store · ${JDS_OPERATIONS_NAME}`;
  if (/^\/setup(\/|$)/.test(pathname)) return `Set up your store · ${JDS_OPERATIONS_NAME}`;
  if (/^\/(owner|admin|staff)(\/|$)/.test(pathname)) return `Owner tools · ${JDS_OPERATIONS_NAME}`;
  return JDS_OPERATIONS_NAME;
}

function setIcons(doc, href) {
  doc.querySelectorAll('link[rel="icon"],link[rel="shortcut icon"],link[rel="apple-touch-icon"]').forEach((icon) => {
    icon.setAttribute("href", href);
    if (icon.getAttribute("rel") === "icon") icon.setAttribute("type", href.endsWith(".svg") ? "image/svg+xml" : "image/png");
  });
}

export function applyOperationsBranding(doc = globalThis.document, pathname = globalThis.location?.pathname || "") {
  if (!doc) return;
  doc.title = operationsTitle(pathname);
  setIcons(doc, JDS_OPERATIONS_ICON);
  doc.querySelector('meta[name="theme-color"]')?.setAttribute("content", JDS_OPERATIONS_THEME);
  const root = doc.documentElement;
  TENANT_VARIABLES.forEach((name) => root.style.removeProperty(name));
  delete root.dataset.tenantTemplate;
  delete root.dataset.tenantTypography;
  delete root.dataset.tenantButtons;
}

export function applyStorefrontBranding(doc = globalThis.document, value) {
  if (!doc || !value) return;
  const colors = value.design?.colors || {};
  const root = doc.documentElement;
  root.style.setProperty("--tenant-primary", colors.primary || "#6f7d5f");
  root.style.setProperty("--tenant-accent", colors.accent || "#b98564");
  root.style.setProperty("--tenant-background", colors.background || "#f7f0e6");
  root.style.setProperty("--tenant-surface", colors.surface || "#ffffff");
  root.style.setProperty("--tenant-text", colors.text || "#2f3328");
  root.dataset.tenantTemplate = value.design?.template || "cozy";
  root.dataset.tenantTypography = value.design?.typography || "classic";
  root.dataset.tenantButtons = value.design?.buttonStyle || "rounded";
  doc.querySelector('meta[name="theme-color"]')?.setAttribute("content", value.design?.pwa?.themeColor || colors.primary || "#6f7d5f");
  const iconUrl = `/api/v1/storefront/icon/192.png?tenant=${encodeURIComponent(value.tenant.id)}&v=${value.designVersion || 0}`;
  doc.querySelectorAll('link[rel="apple-touch-icon"],link[rel="icon"],link[rel="shortcut icon"]').forEach((icon) => { icon.setAttribute("href", iconUrl); if (icon.getAttribute("rel") === "icon") icon.setAttribute("type", "image/png"); });
  doc.title = `${value.business?.displayName || "Order ahead"} · Order online`;
}
