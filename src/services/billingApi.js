// JDS platform billing (shops pay JDS). The backend keeps billing OFF unless JDS_BILLING_ENABLED=true.
async function request(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, { credentials: "same-origin", cache: "no-store", ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body?.detail?.message || (typeof body?.detail === "string" ? body.detail : "") || "Billing is unavailable.");
  return body;
}
export const fetchOwnerBilling = () => request("/owner/billing");
export const saveBillingCard = (sourceId, pkg, csrf) => request("/owner/billing/card", { method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify({ sourceId, package: pkg || null }) });
export const changeBillingPackage = (pkg, extraLocations, csrf) => request("/owner/billing/package", { method: "PUT", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify({ package: pkg, extraLocations }) });
export const fetchPlatformBilling = () => request("/platform/admin/billing");

export const money = (cents) => `$${((cents || 0) / 100).toLocaleString("en-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const STATUS_LABELS = { none: "No card on file", active: "Paid up", past_due: "Payment failed", paused: "Ordering paused", cancelled: "Cancelled", exempt: "Free (beta)" };
export const billingStatusLabel = (status) => STATUS_LABELS[status] || String(status || "").replaceAll("_", " ");

export function formatDate(iso) {
  if (!iso) return null;
  const date = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleDateString("en-CA", { month: "long", day: "numeric", year: "numeric" });
}

/** Plain-language lines for the owner billing card. */
export function billingLines(view) {
  if (!view) return [];
  if (view.freeDuringBeta) return ["Free during the beta — you won't be charged."];
  const lines = [`${view.packageName || "Starter"}: ${money(view.monthlyAmountCents)}/month CAD${view.extraLocations ? ` (includes ${view.extraLocations} extra location${view.extraLocations === 1 ? "" : "s"})` : ""}`];
  if (view.pendingPackage) lines.push(`Changing to ${view.pendingPackage[0].toUpperCase()}${view.pendingPackage.slice(1)} on your next bill.`);
  if (view.nextBillOn) lines.push(`Next bill: ${formatDate(view.nextBillOn)}`);
  lines.push(view.card ? `Card: ${view.card.brand ? `${view.card.brand} ` : ""}ending in ${view.card.last4}` : "No card on file yet.");
  if (view.status === "past_due") lines.push(`Your last payment didn't go through. Please update your card${view.graceEndsAt ? ` before ${formatDate(view.graceEndsAt)}` : ""} to keep online ordering on.`);
  if (view.orderingPaused) lines.push("Online ordering is paused until the payment goes through.");
  return lines;
}

let sdkPromise = null;
export function loadSquareSdk(url, doc = globalThis.document) {
  if (globalThis.Square) return Promise.resolve(globalThis.Square);
  if (!sdkPromise) sdkPromise = new Promise((resolve, reject) => {
    const script = doc.createElement("script");
    script.src = url; script.async = true;
    script.onload = () => (globalThis.Square ? resolve(globalThis.Square) : reject(new Error("Card form unavailable.")));
    script.onerror = () => { sdkPromise = null; reject(new Error("Card form unavailable.")); };
    doc.head.appendChild(script);
  });
  return sdkPromise;
}
