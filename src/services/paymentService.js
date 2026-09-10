/**
 * Provider-neutral payment client (M1).
 * Cart/storefront talk to /api/v1/payments — never provider SDKs or secrets.
 * Clover OAuth/admin connection remains in cloverService.js.
 */

const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || "";

export class PaymentCheckoutError extends Error {
  constructor(message, { cause, code, status } = {}) {
    super(message, { cause });
    this.name = "PaymentCheckoutError";
    this.code = code;
    this.status = status;
  }
}

export class PaymentConnectionError extends Error {
  constructor(message, { cause, code, status } = {}) {
    super(message, { cause });
    this.name = "PaymentConnectionError";
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
    fallbackMessage = "Payments are unavailable.",
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

/** Start electronic checkout for a saved order via the tenant's configured provider. */
export async function createCheckout(
  publicToken,
  { apiBaseUrl = API_BASE_URL, fetchImpl = globalThis.fetch } = {},
) {
  let response;
  try {
    response = await fetchImpl(
      apiUrl(
        `/api/v1/payments/orders/${encodeURIComponent(publicToken)}/checkout`,
        apiBaseUrl,
      ),
      {
        credentials: "include",
        headers: { Accept: "application/json" },
        method: "POST",
      },
    );
  } catch (cause) {
    throw new PaymentCheckoutError(
      "We couldn’t connect to start payment. Your order was saved; please check your connection and try payment again.",
      { cause, code: "network_error" },
    );
  }
  const payload = await readResponse(response, {
    ErrorType: PaymentCheckoutError,
    fallbackMessage: "Your order was saved, but payment is temporarily unavailable.",
  });
  if (
    typeof payload?.checkout_url !== "string" ||
    typeof payload?.checkout_session_id !== "string"
  ) {
    throw new Error("Payment provider returned an invalid checkout response.");
  }
  return payload;
}

export async function fetchPaymentConnection({
  apiBaseUrl = API_BASE_URL,
  fetchImpl = globalThis.fetch,
} = {}) {
  let response;
  try {
    response = await fetchImpl(
      apiUrl("/api/v1/payments/connection", apiBaseUrl),
      {
        credentials: "include",
        headers: { Accept: "application/json" },
      },
    );
  } catch (cause) {
    throw new PaymentConnectionError("Connection to the server failed.", {
      cause,
      code: "network_error",
    });
  }
  return readResponse(response, {
    ErrorType: PaymentConnectionError,
    fallbackMessage: "Unable to determine payment connection status.",
  });
}

/** @deprecated Mock confirm — never mark unpaid/manual as paid in the UI. */
export async function confirmPayment(order) {
  return {
    paid: false,
    status: order?.payment_status || order?.status || "unpaid",
    paymentId: null,
    note: "Electronic confirmation is server-owned via webhooks/reconcile; client must not invent paid state.",
  };
}
