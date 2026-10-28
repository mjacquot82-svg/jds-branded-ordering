// Beta "Report a problem" destination. Set VITE_REPORT_PROBLEM_URL at build time to a
// mailto: address or an https:// form URL. Anything else (or unset) hides the link.
export function reportProblemHref(raw = import.meta.env?.VITE_REPORT_PROBLEM_URL, context = "") {
  const value = typeof raw === "string" ? raw.trim() : "";
  if (!value) return null;
  if (/^mailto:[^\s@]+@[^\s@]+$/i.test(value.split("?")[0])) {
    if (value.includes("?")) return value;
    const subject = encodeURIComponent(`Beta problem report${context ? ` (${context})` : ""}`);
    return `${value}?subject=${subject}`;
  }
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}
