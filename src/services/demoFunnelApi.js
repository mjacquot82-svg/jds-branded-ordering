const DEMO_PATH = "/api/v1/demo";
const OWNER_DEMO_PATH = "/api/v1/owner/demo";

export class DemoFunnelError extends Error {
  constructor(message, { code, status } = {}) {
    super(message);
    this.name = "DemoFunnelError";
    this.code = code;
    this.status = status;
  }
}

function apiBase(apiBaseUrl = "") {
  return `${apiBaseUrl.replace(/\/+$/, "")}`;
}

async function parse(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // ignore
  }
  if (!response.ok) {
    throw new DemoFunnelError(
      payload?.detail?.message || payload?.detail || "Demo request failed.",
      { code: payload?.detail?.code, status: response.status },
    );
  }
  return payload;
}

async function request(path, { apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "", body, csrfToken, method = "GET", fetchImpl = globalThis.fetch } = {}) {
  if (typeof fetchImpl !== "function") throw new DemoFunnelError("Demo API unavailable.");
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  const response = await fetchImpl(`${apiBase(apiBaseUrl)}${path}`, {
    method,
    credentials: "include",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return parse(response);
}

export function fetchDemoPricing(options = {}) {
  return request(`${DEMO_PATH}/pricing`, options);
}

export function fetchDemoPilotConfig(options = {}) {
  return request(`${DEMO_PATH}/pilot-config`, options);
}

export function resendDemoVerification(payload, options = {}) {
  return request(`${DEMO_PATH}/resend-verification`, { ...options, method: "POST", body: payload });
}

export function signupDemo(payload, options = {}) {
  return request(`${DEMO_PATH}/signup`, { ...options, method: "POST", body: payload });
}

export function enterDemo(payload, options = {}) {
  return request(`${DEMO_PATH}/enter`, { ...options, method: "POST", body: payload });
}

export function fetchDemoStatus(options = {}) {
  return request(`${OWNER_DEMO_PATH}/status`, options);
}

export function recordDemoEvent(eventName, metadata = {}, options = {}) {
  return request(`${OWNER_DEMO_PATH}/events`, {
    ...options,
    method: "POST",
    body: { event_name: eventName, metadata },
  });
}

export function requestDemoActivation(payload, options = {}) {
  return request(`${OWNER_DEMO_PATH}/activation-request`, {
    ...options,
    method: "POST",
    body: payload,
  });
}

export function fetchPlatformDemoProspects(options = {}) {
  return request("/api/v1/platform/admin/demo-prospects", options);
}

export function fetchPlatformActivationRequests(options = {}) {
  return request("/api/v1/platform/admin/activation-requests", options);
}

export function promoteDemoToLive(organizationId, options = {}) {
  return request(`/api/v1/platform/admin/organizations/${organizationId}/promote-to-live`, {
    ...options,
    method: "POST",
    body: { confirm: true },
  });
}
