import assert from "node:assert/strict";
import test from "node:test";

import {
  canAccessOwnerPath,
  canEditProducts,
  canManageProductAvailability,
  canManageLunchSpecial,
  operationsLinks,
} from "../../src/auth/ownerProductPermissions.js";

const availabilitySession = { role: "staff", permissions: ["catalog.read", "availability.manage"] };
const editorSession = {
  role: "manager",
  permissions: ["catalog.write", "catalog.publish", "availability.manage", "modifiers.manage"],
};

test("availability managers can use the existing products route without receiving catalog editing", () => {
  assert.equal(canAccessOwnerPath(availabilitySession, "/admin/products"), true);
  assert.equal(canAccessOwnerPath(availabilitySession, "/admin/orders"), false);
  assert.equal(canManageProductAvailability(availabilitySession), true);
  assert.equal(canManageLunchSpecial(availabilitySession), false);
  assert.equal(canEditProducts(availabilitySession), false);
});

test("catalog editing requires the complete existing permission set", () => {
  assert.equal(canEditProducts(editorSession), true);
  assert.equal(canEditProducts({ ...editorSession, permissions: editorSession.permissions.slice(1) }), false);
});

test("existing Owner and Manager routing remains unchanged", () => {
  assert.equal(canAccessOwnerPath({ role: "owner", permissions: [] }, "/admin/orders"), true);
  assert.equal(canAccessOwnerPath({ role: "manager", permissions: [] }, "/admin/scheduling"), true);
  assert.equal(canAccessOwnerPath({ role: "manager", permissions: [] }, "/admin/staff"), false);
  assert.equal(canAccessOwnerPath({ role: "owner", permissions: ["members.manage"] }, "/admin/staff"), true);
});

test("operational navigation follows capabilities without exposing dead ends", () => {
  const session = {
    role: "staff",
    permissions: ["catalog.read", "availability.manage", "orders.read", "orders.fulfill", "communications.announce", "lunch_special.manage"],
  };
  assert.deepEqual(operationsLinks(session).map(({ to }) => to), [
    "/admin",
    "/admin/orders",
    "/admin/products",
    "/admin/communications",
  ]);
  assert.equal(canAccessOwnerPath(session, "/admin"), true);
  assert.equal(canAccessOwnerPath(session, "/admin/orders"), true);
  assert.equal(canAccessOwnerPath(session, "/admin/communications"), true);
  assert.equal(canAccessOwnerPath(session, "/admin/scheduling"), false);
  assert.equal(canManageLunchSpecial(session), true);
  assert.equal(canEditProducts(session), false);
});
