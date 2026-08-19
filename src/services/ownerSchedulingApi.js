const OWNER_SCHEDULING_PATH = "/api/v1/owner/scheduling";

export class OwnerSchedulingError extends Error {
  constructor(message, { status } = {}) {
    super(message);
    this.name = "OwnerSchedulingError";
    this.status = status;
  }
}

async function request(path = "", {
  apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "",
  body,
  csrfToken,
  fetchImpl = globalThis.fetch,
  method = "GET",
} = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let response;
  try {
    response = await fetchImpl(
      `${apiBaseUrl.replace(/\/+$/, "")}${OWNER_SCHEDULING_PATH}${path}`,
      {
        body: body === undefined ? undefined : JSON.stringify(body),
        credentials: "include",
        headers,
        method,
      }
    );
  } catch (cause) {
    throw new OwnerSchedulingError("Unable to reach scheduling.", { cause });
  }
  if (response.status === 204) return null;
  let payload = null;
  try { payload = await response.json(); } catch { /* normalized below */ }
  if (!response.ok) {
    const detail = payload?.detail;
    throw new OwnerSchedulingError(
      (typeof detail === "object" ? detail?.message : detail) || "Scheduling update failed.",
      { status: response.status }
    );
  }
  return payload;
}

export const fetchOwnerScheduling = (options = {}) => request("", options);
export const fetchOwnerSchedulingPreview = (options = {}) => request("/preview", options);
export const updateOwnerOrdering = (orderingMode, csrfToken, options = {}) => request("/ordering", { ...options, body: { ordering_mode: orderingMode }, csrfToken, method: "PUT" });
export const updateOwnerHours = (hours, csrfToken, options = {}) => request("/hours", { ...options, body: { hours }, csrfToken, method: "PUT" });
export const updateOwnerPreferences = (preferences, csrfToken, options = {}) => request("/preferences", { ...options, body: preferences, csrfToken, method: "PUT" });
export const createOwnerClosure = (closure, csrfToken, options = {}) => request("/closures", { ...options, body: closure, csrfToken, method: "POST" });
export const updateOwnerClosure = (closureId, closure, csrfToken, options = {}) => request(`/closures/${encodeURIComponent(closureId)}`, { ...options, body: closure, csrfToken, method: "PUT" });
export async function deleteOwnerClosure(closureId, csrfToken, options = {}) {
  await request(`/closures/${encodeURIComponent(closureId)}`, { ...options, csrfToken, method: "DELETE" });
  return fetchOwnerScheduling(options);
}
