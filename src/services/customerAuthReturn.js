import { readTenantLocalStorage, removeTenantLocalStorage, writeTenantLocalStorage } from "./tenantBrowserState.js";

const AUTH_RETURN_KEY = "guesthouse-customer-auth-return";
const DEFAULT_RETURN = "/account";

export function safeCustomerReturn(value) {
  return value === "/cart" ? value : DEFAULT_RETURN;
}

export function rememberCustomerReturn(value, storage = globalThis.localStorage) {
  const destination = safeCustomerReturn(value);
  if (destination === "/cart") writeTenantLocalStorage(AUTH_RETURN_KEY, destination, storage);
  return destination;
}

export function customerReturnFrom(params, storage = globalThis.localStorage) {
  const requested = params?.get?.("returnTo");
  if (requested) return rememberCustomerReturn(requested, storage);
  return safeCustomerReturn(readTenantLocalStorage(AUTH_RETURN_KEY, storage));
}

export function clearCustomerReturn(storage = globalThis.localStorage) {
  removeTenantLocalStorage(AUTH_RETURN_KEY, storage);
}

export function customerAuthHref(path, destination) {
  const safe = safeCustomerReturn(destination);
  return safe === DEFAULT_RETURN ? path : `${path}?returnTo=${encodeURIComponent(safe)}`;
}
