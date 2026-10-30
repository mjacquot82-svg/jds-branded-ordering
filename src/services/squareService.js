/**
 * Square owner connection + customer payment status check.
 * The browser never sees Square tokens; everything goes through /api/v1/square.
 */

const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || "";

export class SquareConnectionError extends Error {
  constructor(message, { cause, code, status } = {}) {
    super(message, { cause });
    this.name = "SquareConnectionError";
    this.code = code;
    this.status = status;
  }
}

function apiUrl(path, apiBaseUrl = API_BASE_URL) {
  return `${apiBaseUrl.replace(/\/+$/, "")}${path}`;
}

export function getSquareConnectUrl(apiBaseUrl = API_BASE_URL) {
  return apiUrl("/api/v1/square/oauth/start", apiBaseUrl);
}

export async function fetchSquareConnection({ apiBaseUrl = API_BASE_URL, fetchImpl = globalThis.fetch } = {}) {
  let response;
  try {
    response = await fetchImpl(apiUrl("/api/v1/square/connection", apiBaseUrl), {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
  } catch (cause) {
    throw new SquareConnectionError("Connection to the server failed.", { cause, code: "network_error" });
  }
  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    throw new SquareConnectionError(payload?.detail?.message || "Unable to determine Square status.", {
      code: payload?.detail?.code, status: response.status,
    });
  }
  return payload;
}

/** Plain-language heading/detail for the owner's Square card. */
export function describeSquareConnection(connection) {
  if (!connection) return { heading: "Checking…", detail: "Checking your Square connection…" };
  if (connection.health === "reconnect_required") {
    return { heading: "Reconnect needed", detail: "Square needs you to sign in again before customers can pay." };
  }
  if (connection.health === "no_location") {
    return { heading: "No active location", detail: "Your Square account has no active location that can take cards." };
  }
  if (connection.connected) {
    const mode = connection.environment === "sandbox" ? " (test mode)" : "";
    return { heading: "Connected", detail: `Customers can pay by card through Square${mode}.` };
  }
  return { heading: "Not connected", detail: "Connect Square so customers can pay by card when they order." };
}

/** Message for the ?square=… result after returning from Square sign-in. */
export function squareReturnMessage(result) {
  switch (result) {
    case "connected": return "Square is connected.";
    case "cancelled": return "Square wasn’t connected. You can try again any time.";
    case "no_location": return "Square connected, but it has no active location that can take cards.";
    case "error": return "Square couldn’t be connected. Please try again.";
    default: return "";
  }
}

/** Ask the server to check Square directly (fallback when the webhook is slow). Never throws. */
export async function refreshSquarePaymentStatus(
  publicToken,
  { apiBaseUrl = API_BASE_URL, fetchImpl = globalThis.fetch } = {},
) {
  try {
    const response = await fetchImpl(
      apiUrl(`/api/v1/square/orders/${encodeURIComponent(publicToken)}/refresh`, apiBaseUrl),
      { credentials: "include", headers: { Accept: "application/json" }, method: "POST" },
    );
    if (!response.ok) return { paid: false };
    const payload = await response.json();
    return { ...payload, paid: payload?.paid === true };
  } catch {
    return { paid: false };
  }
}
