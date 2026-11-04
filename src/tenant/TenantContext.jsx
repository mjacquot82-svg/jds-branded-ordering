import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { applyOperationsBranding, applyStorefrontBranding, isOperationsPath } from "./operationsBranding.js";

const TenantContext = createContext(null);
export function tenantStorageKey(tenantId, key) { return `jds:${tenantId}:${key}`; }

export function TenantProvider({ children }) {
  const [state, setState] = useState({ status: "loading", value: null });
  // /build is the self-service demo funnel — must not require a resolved café hostname.
  const operationsRoute = /^\/(admin|owner|staff|build|activate|setup|go-live)(\/|$)/.test(globalThis.location?.pathname || "");
  useEffect(() => {
    let active = true;
    const params = new URLSearchParams(globalThis.location?.search || "");
    const reviewTenant = params.get("review_tenant");
    // Beta "shop links" (?shop=<slug>): the API remembers the shop in a cookie when enabled.
    const pilotShop = params.get("shop");
    const query = new URLSearchParams();
    if (reviewTenant) query.set("review_tenant", reviewTenant); else if (pilotShop) query.set("shop", pilotShop);
    // Operations pages on the platform host have no storefront; optional=1 makes the API answer 204 instead of a console-noisy 404.
    if (operationsRoute) query.set("optional", "1");
    const bootstrapUrl = `/api/v1/storefront/bootstrap${query.size ? `?${query}` : ""}`;
    fetch(bootstrapUrl, { cache: "no-store", credentials: "same-origin" })
      .then(async (response) => { if (!response.ok || response.status === 204) throw new Error("Storefront unavailable"); return response.json(); })
      .then((value) => {
        if (!active) return;
        if (value?.tenant?.slug) document.documentElement.dataset.tenantSlug = value.tenant.slug;
        setState({ status: "ready", value });
      })
      .catch(() => { if (active) setState(operationsRoute ? { status: "operations", value: { tenant: { id: "membership-scoped", slug: "operations" }, business: { displayName: "JDS Operations" }, design: {} } } : { status: "error", value: null }); });
    return () => { active = false; delete document.documentElement.dataset.tenantTemplate; delete document.documentElement.dataset.tenantTypography; delete document.documentElement.dataset.tenantButtons; delete document.documentElement.dataset.tenantSlug; };
  }, []);
  const location = useLocation();
  // Operations routes get neutral JDS branding; storefront routes get tenant branding.
  // Re-evaluated on client-side navigation so neither leaks into the other.
  useEffect(() => {
    if (isOperationsPath(location.pathname)) applyOperationsBranding(document, location.pathname);
    else if (state.status === "ready") applyStorefrontBranding(document, state.value);
  }, [location.pathname, state]);
  const context = useMemo(() => ({ ...state, storageKey: (key) => tenantStorageKey(state.value?.tenant?.id || "unresolved", key) }), [state]);
  if (state.status === "loading") return <main className="tenant-gate"><p>{isOperationsPath(location.pathname) ? "Loading…" : "Opening storefront…"}</p></main>;
  if (state.status === "error") {
    // A beta shop link (?shop=) for a café that is still in setup must not look like a dead link.
    if (new URLSearchParams(globalThis.location?.search || "").get("shop")) return <main className="tenant-gate"><h1>Opening soon</h1><p>This café’s ordering app is still being set up. Check back soon, or ask the café for their launch date.</p></main>;
    return <main className="tenant-gate"><h1>Storefront unavailable</h1><p>Check the address and try again.</p></main>;
  }
  return <TenantContext.Provider value={context}>{children}</TenantContext.Provider>;
}
export function useTenant() {
  return useContext(TenantContext) || { status: "ready", value: { tenant: { id: "local-ladels", slug: "the-guest-house" }, business: { displayName: "The Guest House" }, design: { displayName: "The Guest House", tagline: "Café & Pantry" } }, storageKey: (key) => tenantStorageKey("local-ladels", key) };
}
