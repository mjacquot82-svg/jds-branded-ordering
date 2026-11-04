import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { applyOperationsBranding, applyStorefrontBranding, isOperationsPath } from "./operationsBranding.js";

const TenantContext = createContext(null);
export function tenantStorageKey(tenantId, key) { return `jds:${tenantId}:${key}`; }

/** Every shop address printed or shared is <slug>.<base domain>. */
export const DEFAULT_STOREFRONT_BASE_DOMAIN = "order.jdsstudio.ca";
// Same shape and length rules as the API's shop slugs (3-63 chars), so a junk subdomain
// never becomes a shop request the API would silently ignore.
const HOSTED_SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/**
 * Lowercase, drop any scheme, path, port and leading/trailing dots:
 * "ZZ-Test.Order.JDSStudio.ca.:443" -> "zz-test.order.jdsstudio.ca".
 */
function normalizeHostname(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  const withoutScheme = raw.includes("://") ? raw.split("://", 2)[1] : raw;
  const withoutPath = withoutScheme.split("/", 1)[0].replace(/^\[|\]$/g, "").split(":", 1)[0];
  return withoutPath.replace(/^\.+|\.+$/g, "").toLowerCase();
}

/** The storefront base domain: VITE_STOREFRONT_BASE_DOMAIN when set, else order.jdsstudio.ca. */
export function storefrontBaseDomain(env = import.meta.env) {
  return normalizeHostname(env?.VITE_STOREFRONT_BASE_DOMAIN) || DEFAULT_STOREFRONT_BASE_DOMAIN;
}

/**
 * The single shop label directly under the storefront base domain, or null.
 * "zz-test-cafe.order.jdsstudio.ca" -> "zz-test-cafe". The bare base domain, "www", anything
 * deeper than one label ("a.b.order.jdsstudio.ca"), and hosts outside the base domain
 * (the Canner app host, localhost, a bare IP) all return null.
 */
export function shopSlugFromHostname(hostname, baseDomain = storefrontBaseDomain()) {
  const host = normalizeHostname(hostname);
  const base = normalizeHostname(baseDomain);
  if (!host || !base || host === base || !host.endsWith(`.${base}`)) return null;
  const label = host.slice(0, host.length - base.length - 1);
  if (!label || label === "www" || label.length < 3 || label.length > 63) return null;
  return HOSTED_SLUG.test(label) ? label : null;
}

/**
 * Query the storefront bootstrap call should carry.
 * Precedence: ?review_tenant= (unchanged), then ?shop= (unchanged), then the shop the browser
 * itself is on. Canner's edge in front of the API rewrites the forwarded shop hostname and the
 * web proxy's header pair does not survive, so the address bar is the only trustworthy source.
 * On the Canner app host and on localhost no slug is derived and behaviour is unchanged.
 */
export function storefrontBootstrapParams(hostname, search, baseDomain) {
  const params = new URLSearchParams(search || "");
  const reviewTenant = params.get("review_tenant");
  const requestedShop = params.get("shop");
  const hostedShop = shopSlugFromHostname(hostname, baseDomain);
  const query = new URLSearchParams();
  if (reviewTenant) query.set("review_tenant", reviewTenant);
  else if (requestedShop) query.set("shop", requestedShop);
  else if (hostedShop) query.set("shop", hostedShop);
  return query;
}

export function TenantProvider({ children }) {
  const [state, setState] = useState({ status: "loading", value: null });
  // /build is the self-service demo funnel — must not require a resolved café hostname.
  const operationsRoute = /^\/(admin|owner|staff|build|activate|setup|go-live)(\/|$)/.test(globalThis.location?.pathname || "");
  // Beta "shop links" (?shop=<slug>) and hosted shop addresses (<slug>.order.jdsstudio.ca).
  // Resolved from the address bar once: a shop's own subdomain tells the app which shop it is.
  const bootstrapParams = useMemo(() => storefrontBootstrapParams(globalThis.location?.hostname, globalThis.location?.search), []);
  useEffect(() => {
    let active = true;
    const query = new URLSearchParams(bootstrapParams);
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
  }, [bootstrapParams, operationsRoute]);
  const location = useLocation();
  // Operations routes get neutral JDS branding; storefront routes get tenant branding.
  // Re-evaluated on client-side navigation so neither leaks into the other.
  useEffect(() => {
    if (isOperationsPath(location.pathname)) applyOperationsBranding(document, location.pathname);
    else if (state.status === "ready") applyStorefrontBranding(document, state.value, bootstrapParams);
  }, [location.pathname, state, bootstrapParams]);
  const context = useMemo(() => ({ ...state, storageKey: (key) => tenantStorageKey(state.value?.tenant?.id || "unresolved", key) }), [state]);
  if (state.status === "loading") return <main className="tenant-gate"><p>{isOperationsPath(location.pathname) ? "Loading…" : "Opening storefront…"}</p></main>;
  if (state.status === "error") {
    // A shop that is still in setup must not look like a dead link, whether it was named with
    // ?shop= or opened on its own <slug>.order.jdsstudio.ca address.
    if (bootstrapParams.get("shop")) return <main className="tenant-gate"><h1>Opening soon</h1><p>This café’s ordering app is still being set up. Check back soon, or ask the café for their launch date.</p></main>;
    return <main className="tenant-gate"><h1>Storefront unavailable</h1><p>Check the address and try again.</p></main>;
  }
  return <TenantContext.Provider value={context}>{children}</TenantContext.Provider>;
}
export function useTenant() {
  return useContext(TenantContext) || { status: "ready", value: { tenant: { id: "local-ladels", slug: "the-guest-house" }, business: { displayName: "The Guest House" }, design: { displayName: "The Guest House", tagline: "Café & Pantry" } }, storageKey: (key) => tenantStorageKey("local-ladels", key) };
}
