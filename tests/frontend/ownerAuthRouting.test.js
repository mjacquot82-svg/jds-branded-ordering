import assert from "node:assert/strict";
import test from "node:test";

import {
  ownerLoginDestination,
  safeAdminReturnTo,
} from "../../src/auth/ownerAuthRouting.js";

test("admin authentication preserves the complete original destination", () => {
  assert.equal(
    ownerLoginDestination({ pathname: "/admin/products", search: "?category=coffee", hash: "#editing" }),
    "/admin/products?category=coffee#editing"
  );
});

test("owner login accepts only internal admin return destinations", () => {
  assert.equal(safeAdminReturnTo("/admin/orders?state=open"), "/admin/orders?state=open");
  assert.equal(safeAdminReturnTo("https://attacker.example/admin"), "/admin");
  assert.equal(safeAdminReturnTo("//attacker.example/admin"), "/admin");
  assert.equal(safeAdminReturnTo("/administrator"), "/admin");
  assert.equal(safeAdminReturnTo("/cart"), "/admin");
  assert.equal(safeAdminReturnTo(null), "/admin");
});
