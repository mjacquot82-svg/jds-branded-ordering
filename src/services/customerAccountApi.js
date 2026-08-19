const CUSTOMER_PATH = "/api/v1/customer";
import { getApiErrorMessage } from "./customerMessages.js";

async function request(path, { body, csrfToken, method = "GET", fetchImpl = globalThis.fetch, apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "" } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let response;
  try {
    response = await fetchImpl(`${apiBaseUrl.replace(/\/+$/, "")}${CUSTOMER_PATH}${path}`, {
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: method === "GET" ? "no-store" : undefined,
      credentials: "include",
      headers,
      method,
    });
  } catch {
    throw new Error("Unable to reach the customer account service. Please check your connection and try again.");
  }
  let payload = null;
  try { payload = await response.json(); } catch { /* normalized below */ }
  if (!response.ok) throw new Error(getApiErrorMessage(payload, "We couldn’t update your account. Please try again."));
  if (payload === null) throw new Error("The customer account service returned an invalid response.");
  return payload;
}

export const fetchCustomerProfile = (options = {}) => request("/profile", options);
export const updateCustomerProfile = (profile, csrfToken, options = {}) => request("/profile", { ...options, body: profile, csrfToken, method: "PUT" });
export const fetchCustomerOrders = (options = {}) => request("/orders", options);
export const fetchCustomerOrder = (orderId, options = {}) => request(`/orders/${encodeURIComponent(orderId)}`, options);
export const fetchCustomerQuickOrder = (options = {}) => request("/quick-order", options);
