export function ownerLoginDestination(location) {
  return `${location.pathname}${location.search || ""}${location.hash || ""}`;
}

export function safeAdminReturnTo(value) {
  const isAdminPath = typeof value === "string" && (
    value === "/admin" ||
    value.startsWith("/admin/") ||
    value.startsWith("/admin?") ||
    value.startsWith("/admin#")
  );
  return isAdminPath && !value.startsWith("//")
    ? value
    : "/admin";
}

export function ownerEntryPath(session, returnTo = "/admin") {
  if (["owner", "manager"].includes(session?.role) && session?.app_launched === false) {
    const allowed = new Set(["welcome","look","brand","business","catalog","ordering","payments","preview","launch"]);
    const step = allowed.has(session.onboarding_current_step) ? session.onboarding_current_step : "welcome";
    return `/setup/${step}`;
  }
  if (returnTo !== "/admin") return returnTo;
  return "/admin";
}
