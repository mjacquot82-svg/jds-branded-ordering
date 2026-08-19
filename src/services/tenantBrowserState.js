export function tenantBrowserKey(key, hostname = globalThis.location?.hostname || "local") {
  return `jds:${String(hostname).toLowerCase()}:${key}`;
}

export function readTenantLocalStorage(key, storage = globalThis.localStorage) {
  const scoped = storage?.getItem(tenantBrowserKey(key));
  if (scoped != null) return scoped;
  const host = globalThis.location?.hostname || "local";
  if (["localhost", "127.0.0.1", "test", "local"].includes(host)) {
    const legacy = storage?.getItem(key);
    if (legacy != null) { storage?.setItem(tenantBrowserKey(key), legacy); return legacy; }
  }
  return null;
}

export function writeTenantLocalStorage(key, value, storage = globalThis.localStorage) {
  storage?.setItem(tenantBrowserKey(key), value);
  if (["localhost", "127.0.0.1", "test", "local"].includes(globalThis.location?.hostname || "local")) storage?.setItem(key, value);
}

export function removeTenantLocalStorage(key, storage = globalThis.localStorage) {
  storage?.removeItem(tenantBrowserKey(key));
  if (["localhost", "127.0.0.1", "test", "local"].includes(globalThis.location?.hostname || "local")) storage?.removeItem(key);
}
