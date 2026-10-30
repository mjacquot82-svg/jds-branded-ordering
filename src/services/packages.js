// Fallback copy of the package list (the API at /api/v1/packages is the source of truth).
export const BETA_NOTICE = "Free during the beta — you won't be charged. We'll give you 30 days' notice before any charge.";
export const PACKAGE_NOTES = ["Extra locations: $75/month each", "Custom features: ask us"];
export const PACKAGES = [
  { key: "starter", name: "Starter", amountCents: 15000, currency: "CAD", interval: "month", features: [
    { label: "Your own branded app" }, { label: "Menu with options" }, { label: "Online ordering & card payment with pickup times" },
    { label: "Order screen" }, { label: "Email receipts" }, { label: "Refunds" }, { label: "Marketing kit" },
  ] },
  { key: "plus", name: "Plus", amountCents: 22500, currency: "CAD", interval: "month", includes: "Everything in Starter, plus:", features: [
    { label: "Loyalty rewards" }, { label: "Announcements & push alerts" }, { label: "Customer list" }, { label: "Staff PIN logins" },
  ] },
  { key: "pro", name: "Pro", amountCents: 30000, currency: "CAD", interval: "month", includes: "Everything in Plus, plus:", features: [
    { label: "'Order ready' text alerts (300/month included)", comingSoon: true }, { label: "Sales reports", comingSoon: true },
    { label: "Your own web address", comingSoon: true }, { label: "Priority support" },
  ] },
];
const STORAGE_KEY = "jds.build.selectedPackage";
export const isPackageKey = (value) => PACKAGES.some((item) => item.key === value);
export const packageName = (key) => PACKAGES.find((item) => item.key === key)?.name || null;
export const packagePrice = (item) => `$${Math.round(item.amountCents / 100)}/month`;
export function rememberPackage(key, storage = globalThis.localStorage) { try { if (isPackageKey(key)) storage?.setItem(STORAGE_KEY, key); } catch { /* private mode */ } }
export function rememberedPackage(storage = globalThis.localStorage) { try { const value = storage?.getItem(STORAGE_KEY); return isPackageKey(value) ? value : null; } catch { return null; } }
export function forgetPackage(storage = globalThis.localStorage) { try { storage?.removeItem(STORAGE_KEY); } catch { /* ignore */ } }
