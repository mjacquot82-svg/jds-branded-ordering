import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { reportProblemHref } from "../../src/config/reportProblem.js";

test("unset or unsafe values hide the link", () => {
  for (const v of [undefined, "", "  ", "http://x.test/form", "javascript:alert(1)", "mailto:", "not a url"]) assert.equal(reportProblemHref(v), null);
});
test("mailto gets a subject with context", () => {
  assert.equal(reportProblemHref("mailto:beta@example.test", "customer"), "mailto:beta@example.test?subject=Beta%20problem%20report%20(customer)");
  assert.equal(reportProblemHref("mailto:beta@example.test?subject=x"), "mailto:beta@example.test?subject=x");
});
test("https forms pass through", () => {
  assert.equal(reportProblemHref("https://forms.example.test/beta"), "https://forms.example.test/beta");
});
test("link is wired into customer footer and admin dashboard", async () => {
  const layout = await readFile(new URL("../../src/layouts/AppLayout.jsx", import.meta.url), "utf8");
  const admin = await readFile(new URL("../../src/admin/AdminDashboard.jsx", import.meta.url), "utf8");
  assert.match(layout, /<ReportProblemLink context="customer"/);
  assert.match(admin, /<ReportProblemLink context="shop admin"/);
});
