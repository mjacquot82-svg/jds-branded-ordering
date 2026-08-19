const AUTH_PATH = "/api/v1/customer/auth";
import { getApiErrorMessage } from "./customerMessages.js";

export class CustomerAuthError extends Error {
  constructor(message, { code, status } = {}) {
    super(message);
    this.name = "CustomerAuthError";
    this.code = code;
    this.status = status;
  }
}

async function request(path, { body, csrfToken, method = "GET", fetchImpl = globalThis.fetch, apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "" } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let response;
  try {
    response = await fetchImpl(`${apiBaseUrl.replace(/\/+$/, "")}${AUTH_PATH}${path}`, {
      body: body === undefined ? undefined : JSON.stringify(body), credentials: "include", headers, method,
    });
  } catch (cause) {
    throw new CustomerAuthError("Unable to reach customer authentication.", { cause });
  }
  let payload = null;
  try { payload = await response.json(); } catch { /* normalized below */ }
  if (!response.ok) {
    throw new CustomerAuthError(getApiErrorMessage(payload, "Customer authentication failed."), {
      code: payload?.detail?.code, status: response.status,
    });
  }
  return payload;
}

export const fetchCustomerSession = (options = {}) => request("/session", options);
export const loginCustomer = (email, password, { keepSignedIn = false, ...options } = {}) => request("/login", { ...options, body: { email, keep_signed_in: keepSignedIn, password }, method: "POST" });
export const registerCustomer = (displayName, email, password, phone, options = {}) => request("/register", { ...options, body: { display_name: displayName, email, password, phone }, method: "POST" });
export const verifyCustomerEmail = (tokenHash, options = {}) => request("/verify-email", { ...options, body: { token_hash: tokenHash }, method: "POST" });
export const resendCustomerVerification = (email, options = {}) => request("/verification/resend", { ...options, body: { email }, method: "POST" });
export const requestCustomerPasswordReset = (email, options = {}) => request("/password-reset", { ...options, body: { email }, method: "POST" });
export const completeCustomerPasswordReset = ({ accessToken, password, tokenHash }, options = {}) => request("/password-reset/complete", { ...options, body: { access_token: accessToken || undefined, password, token_hash: tokenHash || undefined }, method: "POST" });
export const logoutCustomer = (csrfToken, options = {}) => request("/logout", { ...options, csrfToken, method: "POST" });
