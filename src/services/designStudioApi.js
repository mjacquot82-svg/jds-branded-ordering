async function request(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, { credentials: "same-origin", cache: "no-store", ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body?.detail?.message || body?.detail || "Design Studio is unavailable.");
  return body;
}
export const fetchDesignDraft = () => request("/owner/design");
export const fetchDesignVersions = () => request("/owner/design/versions");
export const saveDesignDraft = (value, csrf) => request("/owner/design", { method: "PUT", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify(value) });
export const publishDesign = (csrf) => request("/owner/design/publish", { method: "POST", headers: { "X-CSRF-Token": csrf } });
export const revertDesign = (versionId, csrf) => request("/owner/design/revert", { method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify({ version_id: versionId }) });
export const fetchBusinesses = () => request("/owner/businesses");
export const fetchOnboarding = () => request("/owner/onboarding");
export const saveOnboarding = (value, csrf) => request("/owner/onboarding", { method: "PUT", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify(value) });
export const fetchBusinessProfile = () => request("/owner/business-profile");
export const saveBusinessProfile = (value, csrf) => request("/owner/business-profile", { method: "PUT", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify(value) });
export const fetchPlatformOrganizations = () => request("/platform/admin/organizations");
