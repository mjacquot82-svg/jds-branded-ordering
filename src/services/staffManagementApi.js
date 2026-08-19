const API_ROOT = "/api/v1/owner/staff";

async function request(path = "", { body, csrfToken, method = "GET" } = {}) {
  const headers = { Accept: "application/json" };
  if (body) headers["Content-Type"] = "application/json";
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  const apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "";
  const response = await fetch(`${apiBaseUrl.replace(/\/+$/, "")}${API_ROOT}${path}`, {
    body: body ? JSON.stringify(body) : undefined, credentials: "include", headers, method,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail?.message || payload?.detail || "Staff access could not be updated.");
  return payload;
}

export const fetchStaffAccounts = async () => {
  const accounts = await request();
  if (!Array.isArray(accounts)) throw new Error("Staff access returned an invalid response.");
  return accounts;
};
export const createStaffAccount = (displayName, pin, csrfToken) => request("", { body: { display_name: displayName, pin }, csrfToken, method: "POST" });
export const resetStaffPin = (id, pin, csrfToken) => request(`/${id}/pin`, { body: { pin }, csrfToken, method: "PUT" });
export const setStaffAccessStatus = (id, active, csrfToken) => request(`/${id}/status`, { body: { active }, csrfToken, method: "PUT" });
