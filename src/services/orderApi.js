const ORDERS_PATH = "/api/v1/orders";

export class OrderApiError extends Error {
  constructor(message, { cause, code, status } = {}) {
    super(message, { cause });
    this.name = "OrderApiError";
    this.code = code;
    this.status = status;
  }
}

function getOrdersUrl(apiBaseUrl = "") {
  return `${apiBaseUrl.replace(/\/+$/, "")}${ORDERS_PATH}`;
}

async function parseJson(response) {
  try {
    return await response.json();
  } catch (cause) {
    throw new OrderApiError("The order service returned an invalid response.", {
      cause,
      status: response.status,
    });
  }
}

function requireOrder(payload, status) {
  if (
    !payload ||
    typeof payload !== "object" ||
    typeof payload.public_token !== "string" ||
    !["pending", "payment_pending", "paid", "payment_failed"].includes(
      payload.status
    ) ||
    !payload.customer ||
    !Array.isArray(payload.items)
  ) {
    throw new OrderApiError("The order response has an invalid shape.", {
      status,
    });
  }

  return payload;
}

async function requestOrder(url, options, fetchImpl) {
  if (typeof fetchImpl !== "function") {
    throw new OrderApiError("Order requests are unavailable.");
  }

  let response;
  try {
    response = await fetchImpl(url, options);
  } catch (cause) {
    throw new OrderApiError("Unable to reach the order service.", { cause });
  }

  const payload = await parseJson(response);
  if (!response.ok) {
    const detail = payload?.detail;
    throw new OrderApiError(
      typeof detail?.message === "string"
        ? detail.message
        : "The order service returned an error.",
      {
        code: typeof detail?.code === "string" ? detail.code : undefined,
        status: response.status,
      }
    );
  }

  return requireOrder(payload, response.status);
}

export function createPendingOrder(
  payload,
  {
    apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "",
    fetchImpl = globalThis.fetch,
    signal,
  } = {}
) {
  return requestOrder(
    getOrdersUrl(apiBaseUrl),
    {
      body: JSON.stringify(payload),
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      credentials: "include",
      method: "POST",
      signal,
    },
    fetchImpl
  );
}

export function fetchPendingOrder(
  publicToken,
  {
    apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "",
    fetchImpl = globalThis.fetch,
    signal,
  } = {}
) {
  return requestOrder(
    `${getOrdersUrl(apiBaseUrl)}/${encodeURIComponent(publicToken)}`,
    {
      credentials: "include",
      headers: { Accept: "application/json" },
      method: "GET",
      signal,
    },
    fetchImpl
  );
}
