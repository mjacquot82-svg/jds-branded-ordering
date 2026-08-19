const OWNER_AUTH_PATH = "/api/v1/owner/auth";

export class OwnerAuthError extends Error {
  constructor(message, { code, status } = {}) {
    super(message);
    this.name = "OwnerAuthError";
    this.code = code;
    this.status = status;
  }
}

function authUrl(path, apiBaseUrl = "") {
  return `${apiBaseUrl.replace(/\/+$/, "")}${OWNER_AUTH_PATH}${path}`;
}

async function parseResponse(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // Invalid error bodies are normalized below.
  }
  if (!response.ok) {
    throw new OwnerAuthError(
      payload?.detail?.message || "Owner authentication is unavailable.",
      { code: payload?.detail?.code, status: response.status }
    );
  }
  return payload;
}

async function ownerAuthRequest(
  path,
  { apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "", body, csrfToken, fetchImpl = globalThis.fetch, method = "GET", signal } = {}
) {
  if (typeof fetchImpl !== "function") {
    throw new OwnerAuthError("Owner authentication is unavailable.");
  }
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let response;
  try {
    response = await fetchImpl(authUrl(path, apiBaseUrl), {
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "include",
      headers,
      method,
      signal,
    });
  } catch (cause) {
    throw new OwnerAuthError("Unable to reach owner authentication.", { cause });
  }
  return parseResponse(response);
}

export function fetchOwnerSession(options = {}) {
  return ownerAuthRequest("/session", options);
}

export function loginOwner(email, password, options = {}) {
  return ownerAuthRequest("/login", { ...options, body: { email, password }, method: "POST" });
}

export function fetchStaffAccessOptions(options = {}) {
  return staffAccessRequest("/accounts", options);
}

export function loginStaff(staffId, pin, options = {}) {
  return staffAccessRequest("/login", { ...options, body: { staff_id: staffId, pin }, method: "POST" });
}

async function staffAccessRequest(path, { apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "", body, fetchImpl = globalThis.fetch, method = "GET" } = {}) {
  let response;
  try {
    response = await fetchImpl(`${apiBaseUrl.replace(/\/+$/, "")}/api/v1/staff/access${path}`, {
      body: body === undefined ? undefined : JSON.stringify(body), credentials: "include",
      headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) }, method,
    });
  } catch (cause) {
    throw new OwnerAuthError("Unable to reach Staff Access.", { cause });
  }
  return parseResponse(response);
}

export function logoutOwner(csrfToken, options = {}) {
  return ownerAuthRequest("/logout", { ...options, csrfToken, method: "POST" });
}

export function isUnauthenticatedOwnerError(error) {
  return error instanceof OwnerAuthError && error.status === 401;
}
