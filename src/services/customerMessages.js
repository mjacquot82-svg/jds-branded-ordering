export function getApiErrorMessage(payload, fallback) {
  const detail = payload?.detail;
  if (typeof detail?.message === "string" && detail.message.trim()) return detail.message;
  if (typeof detail === "string" && detail.trim()) return detail;
  return fallback;
}

export function getCustomerErrorMessage(error, fallback) {
  const message = typeof error?.message === "string" ? error.message.trim() : "";
  return message && message !== "[object Object]" ? message : fallback;
}
