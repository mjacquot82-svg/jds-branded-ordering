const catalogEditingPermissions = [
  "catalog.write",
  "catalog.publish",
  "availability.manage",
  "modifiers.manage",
];

export function canManageProductAvailability(session) {
  return session?.permissions?.includes("availability.manage") === true;
}

export function canManageLunchSpecial(session) {
  return session?.permissions?.includes("lunch_special.manage") === true;
}

export function hasPermission(session, permission) {
  return session?.permissions?.includes(permission) === true;
}

export function isOperationsAdministrator(session) {
  return ["owner", "manager"].includes(session?.role);
}

export function canEditProducts(session) {
  const permissions = new Set(session?.permissions || []);
  return catalogEditingPermissions.every((permission) => permissions.has(permission));
}

export function canAccessOwnerPath(session, pathname) {
  if (pathname === "/admin/loyalty") return hasPermission(session, "loyalty.manage");
  if (pathname === "/admin/staff") return hasPermission(session, "members.manage");
  if (isOperationsAdministrator(session)) return true;
  if (pathname === "/admin") return operationsLinks(session).length > 0;
  if (pathname === "/admin/orders") return hasPermission(session, "orders.read");
  if (pathname === "/admin/products") {
    return hasPermission(session, "catalog.read") && canManageProductAvailability(session);
  }
  if (pathname === "/admin/communications") return hasPermission(session, "communications.announce");
  return false;
}

export function operationsLinks(session) {
  const links = [];
  if (isOperationsAdministrator(session) || session?.permissions?.length) {
    links.push({ end: true, label: "Overview", to: "/admin" });
  }
  if (isOperationsAdministrator(session) || hasPermission(session, "orders.read")) {
    links.push({ label: "Orders", to: "/admin/orders" });
  }
  if (isOperationsAdministrator(session) || (
    hasPermission(session, "catalog.read") && canManageProductAvailability(session)
  )) {
    links.push({ label: "Products", to: "/admin/products" });
  }
  if (isOperationsAdministrator(session)) {
    links.push({ label: "Scheduling", to: "/admin/scheduling" });
  }
  if (isOperationsAdministrator(session) || hasPermission(session, "communications.announce")) {
    links.push({ label: "Communications", to: "/admin/communications" });
  }
  if (hasPermission(session, "loyalty.manage")) links.push({ label: "Loyalty", to: "/admin/loyalty" });
  if (hasPermission(session, "members.manage")) links.push({ label: "Staff", to: "/admin/staff" });
  return links;
}
