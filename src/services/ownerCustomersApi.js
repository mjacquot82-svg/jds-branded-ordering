export async function fetchOwnerCustomers(query = "", { signal } = {}) {
  const response = await fetch(`/api/v1/owner/customers?q=${encodeURIComponent(query)}`, {
    cache: "no-store",
    credentials: "include",
    headers: { Accept: "application/json" },
    signal,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail?.message || "Customers are unavailable.");
  return payload?.customers || [];
}
