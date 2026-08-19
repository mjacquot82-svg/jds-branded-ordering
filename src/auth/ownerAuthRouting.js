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
