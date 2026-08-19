const OWNER_ORDERS_PATH = "/api/v1/owner/orders";

export class OwnerOrdersError extends Error {
  constructor(message, { code, status, cause } = {}) {
    super(message, { cause });
    this.name = "OwnerOrdersError";
    this.code = code;
    this.status = status;
  }
}

async function request(path, {
  apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "",
  body,
  csrfToken,
  fetchImpl = globalThis.fetch,
  method = "GET",
  signal,
} = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let response;
  try {
    response = await fetchImpl(
      `${apiBaseUrl.replace(/\/+$/, "")}${OWNER_ORDERS_PATH}${path}`,
      {
        body: body === undefined ? undefined : JSON.stringify(body),
        credentials: "include",
        headers,
        method,
        signal,
      },
    );
  } catch (cause) {
    throw new OwnerOrdersError("Unable to reach orders.", { cause });
  }
  let payload;
  try { payload = await response.json(); } catch (cause) {
    throw new OwnerOrdersError("Orders returned an invalid response.", {
      cause,
      status: response.status,
    });
  }
  if (!response.ok) {
    throw new OwnerOrdersError(
      payload?.detail?.message || "The order request could not be completed.",
      { code: payload?.detail?.code, status: response.status },
    );
  }
  return payload;
}

export const fetchActiveOwnerOrders = (options = {}) => request("/active", options);
export const fetchOwnerOrderHistory = (options = {}) => request("/history", options);
export const fetchOwnerOrderSummary = (options = {}) => request("/summary", options);
export const fetchOwnerOrder = (orderId, options = {}) => request(`/${encodeURIComponent(orderId)}`, options);
export const updateOwnerOrderFulfillment = (orderId, status, expectedVersion, csrfToken, options = {}) => request(
  `/${encodeURIComponent(orderId)}/fulfillment`,
  {
    ...options,
    body: { expected_version: expectedVersion, status },
    csrfToken,
    method: "PATCH",
  },
);
