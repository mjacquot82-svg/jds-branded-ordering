const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || "";

export class CloverCheckoutError extends Error {
  constructor(message, { cause, code, status } = {}) {
    super(message, { cause });
    this.name = "CloverCheckoutError";
    this.code = code;
    this.status = status;
  }
}

export class CloverConnectionError extends Error {
  constructor(message, { cause, code, status } = {}) {
    super(message, { cause });
    this.name = "CloverConnectionError";
    this.code = code;
    this.status = status;
  }
}

function apiUrl(path, apiBaseUrl = API_BASE_URL) {
  return `${apiBaseUrl.replace(/\/+$/, "")}${path}`;
}

async function readResponse(
  response,
  {
    ErrorType = Error,
    fallbackMessage = "Clover is unavailable.",
  } = {},
) {
  let payload;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new ErrorType(
      payload?.detail?.message || fallbackMessage,
      { code: payload?.detail?.code, status: response.status },
    );
  }
  return payload;
}

export async function createCloverCheckout(
  publicToken,
  { apiBaseUrl = API_BASE_URL, fetchImpl = globalThis.fetch } = {}
) {
  let response;
  try {
    response = await fetchImpl(
      apiUrl(
        `/api/v1/clover/orders/${encodeURIComponent(publicToken)}/checkout`,
        apiBaseUrl
      ),
      {
        credentials: "include",
        headers: { Accept: "application/json" },
        method: "POST",
      }
    );
  } catch (cause) {
    throw new CloverCheckoutError(
      "We couldn’t connect to start payment. Your order was saved; please check your connection and try payment again.",
      { cause, code: "network_error" },
    );
  }
  const payload = await readResponse(response, {
    ErrorType: CloverCheckoutError,
    fallbackMessage: "Your order was saved, but payment is temporarily unavailable.",
  });
  if (
    typeof payload?.checkout_url !== "string" ||
    typeof payload?.checkout_session_id !== "string"
  ) {
    throw new Error("Clover returned an invalid checkout response.");
  }
  return payload;
}

export async function fetchCloverConnection({
  apiBaseUrl = API_BASE_URL,
  fetchImpl = globalThis.fetch,
} = {}) {
  let response;
  try {
    response = await fetchImpl(
      apiUrl("/api/v1/clover/connection", apiBaseUrl),
      {
        credentials: "include",
        headers: { Accept: "application/json" },
      },
    );
  } catch (cause) {
    throw new CloverConnectionError("Connection to the server failed.", {
      cause,
      code: "network_error",
    });
  }
  return readResponse(response, {
    ErrorType: CloverConnectionError,
    fallbackMessage: "Unable to determine Clover status.",
  });
}

export function getCloverConnectUrl(apiBaseUrl = API_BASE_URL) {
  return apiUrl("/api/v1/clover/oauth/start", apiBaseUrl);
}
