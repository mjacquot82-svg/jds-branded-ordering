const PATH = "/api/v1/owner/order-settings";

export const ORDER_SETTINGS_DEFAULTS = Object.freeze({
  pay_at_pickup_enabled: false,
  pay_at_pickup_min_completed_orders: 1,
  pay_at_pickup_max_total_cents: 2500,
  new_order_alert_email: null,
});

async function request({ apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "", body, csrfToken, fetchImpl = globalThis.fetch, method = "GET" } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let response;
  try {
    response = await fetchImpl(`${apiBaseUrl.replace(/\/+$/, "")}${PATH}`, {
      body: body === undefined ? undefined : JSON.stringify(body), credentials: "include", headers, method,
    });
  } catch (cause) {
    throw new Error("Unable to reach order settings.", { cause });
  }
  let payload = null;
  try { payload = await response.json(); } catch { /* handled below */ }
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail?.message === "string" ? detail.message
      : Array.isArray(detail) ? "Check the order settings and try again." : "Order settings could not be saved.";
    throw new Error(message);
  }
  return payload;
}

export const fetchOrderSettings = (options = {}) => request(options);

export function buildOrderSettingsPayload(draft) {
  const dollars = Number(draft.max_total_dollars);
  return {
    pay_at_pickup_enabled: Boolean(draft.pay_at_pickup_enabled),
    pay_at_pickup_min_completed_orders: Math.max(0, Math.min(100, Math.trunc(Number(draft.pay_at_pickup_min_completed_orders) || 0))),
    pay_at_pickup_max_total_cents: Number.isFinite(dollars) ? Math.max(100, Math.min(100000, Math.round(dollars * 100))) : 2500,
    new_order_alert_email: String(draft.new_order_alert_email || "").trim() || null,
  };
}

export const saveOrderSettings = (draft, csrfToken, options = {}) => request({
  ...options, body: buildOrderSettingsPayload(draft), csrfToken, method: "PUT",
});
