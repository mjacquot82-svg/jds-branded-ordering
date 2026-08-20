import { createContext, useContext, useEffect, useMemo, useState } from "react";

const TenantContext = createContext(null);
export function tenantStorageKey(tenantId, key) { return `jds:${tenantId}:${key}`; }

export function TenantProvider({ children }) {
  const [state, setState] = useState({ status: "loading", value: null });
  const operationsRoute = /^\/(admin|owner|staff)(\/|$)/.test(globalThis.location?.pathname || "");
  useEffect(() => {
    let active = true;
    const reviewTenant = new URLSearchParams(globalThis.location?.search || "").get("review_tenant");
    const bootstrapUrl = `/api/v1/storefront/bootstrap${reviewTenant ? `?review_tenant=${encodeURIComponent(reviewTenant)}` : ""}`;
    fetch(bootstrapUrl, { cache: "no-store", credentials: "same-origin" })
      .then(async (response) => { if (!response.ok) throw new Error("Storefront unavailable"); return response.json(); })
      .then((value) => {
        if (!active) return;
        const colors = value.design?.colors || {};
        document.documentElement.style.setProperty("--tenant-primary", colors.primary || "#6f7d5f");
        document.documentElement.style.setProperty("--tenant-accent", colors.accent || "#b98564");
        document.documentElement.style.setProperty("--tenant-background", colors.background || "#f7f0e6");
        document.documentElement.style.setProperty("--tenant-surface", colors.surface || "#ffffff");
        document.documentElement.style.setProperty("--tenant-text", colors.text || "#2f3328");
        document.documentElement.dataset.tenantTemplate = value.design?.template || "cozy";
        document.documentElement.dataset.tenantTypography = value.design?.typography || "classic";
        document.documentElement.dataset.tenantButtons = value.design?.buttonStyle || "rounded";
        const theme = document.querySelector('meta[name="theme-color"]');
        if (theme) theme.setAttribute("content", value.design?.pwa?.themeColor || colors.primary || "#6f7d5f");
        const touchIcon = document.querySelector('link[rel="apple-touch-icon"]');
        const iconUrl = `/api/v1/storefront/icon/192.png?tenant=${encodeURIComponent(value.tenant.id)}&v=${value.designVersion || 0}`;
        if (touchIcon) touchIcon.setAttribute("href", iconUrl);
        document.querySelectorAll('link[rel="icon"],link[rel="shortcut icon"]').forEach((icon) => icon.setAttribute("href", iconUrl));
        document.title = `${value.business?.displayName || "Order ahead"} · Order online`;
        setState({ status: "ready", value });
      })
      .catch(() => { if (active) setState(operationsRoute ? { status: "operations", value: { tenant: { id: "membership-scoped", slug: "operations" }, business: { displayName: "JDS Operations" }, design: {} } } : { status: "error", value: null }); });
    return () => { active = false; delete document.documentElement.dataset.tenantTemplate; delete document.documentElement.dataset.tenantTypography; delete document.documentElement.dataset.tenantButtons; };
  }, []);
  const context = useMemo(() => ({ ...state, storageKey: (key) => tenantStorageKey(state.value?.tenant?.id || "unresolved", key) }), [state]);
  if (state.status === "loading") return <main className="tenant-gate"><p>Opening storefront…</p></main>;
  if (state.status === "error") return <main className="tenant-gate"><h1>Storefront unavailable</h1><p>Check the address and try again.</p></main>;
  return <TenantContext.Provider value={context}>{children}</TenantContext.Provider>;
}
export function useTenant() {
  return useContext(TenantContext) || { status: "ready", value: { tenant: { id: "local-ladels", slug: "the-guest-house" }, business: { displayName: "The Guest House" }, design: { displayName: "The Guest House", tagline: "Café & Pantry" } }, storageKey: (key) => tenantStorageKey("local-ladels", key) };
}
