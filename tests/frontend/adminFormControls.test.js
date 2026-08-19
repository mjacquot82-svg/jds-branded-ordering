import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("Owner and Staff data-entry controls share the Ladel's control treatment", async () => {
  const css = await source("../../src/style.css");

  assert.match(css, /Ladel's Owner and Staff form-control system/);
  assert.match(css, /\.admin-products-page,[\s\S]*?\.modifier-manager,[\s\S]*?\.communication-page,[\s\S]*?\.loyalty-admin-page,[\s\S]*?\.owner-scheduling-page/);
  assert.match(css, /background: var\(--surface-warm\);[\s\S]*?border: 1px solid var\(--border\);[\s\S]*?border-radius: 12px/);
  assert.match(css, /min-height: 48px/);
  assert.match(css, /:focus-visible \{[\s\S]*?border-color: var\(--sage-ink\);[\s\S]*?box-shadow: 0 0 0 4px rgba\(95, 109, 84, \.17\)/);
  assert.match(css, /:disabled \{[\s\S]*?cursor: not-allowed/);
  assert.match(css, /\[readonly\] \{[\s\S]*?cursor: default/);
  assert.match(css, /\[aria-invalid="true"\], :user-invalid/);
});

test("modifier Name and price controls use the shared system without changing money behavior", async () => {
  const [css, manager, money] = await Promise.all([
    source("../../src/style.css"),
    source("../../src/admin/ModifierManager.jsx"),
    source("../../src/services/modifierMoney.js"),
  ]);

  assert.match(css, /\.modifier-edit-row label[\s\S]*?font-weight: 800/);
  assert.match(css, /\.modifier-manager \.money-input b[\s\S]*?background: var\(--surface-soft\)/);
  assert.match(css, /\.modifier-manager \.money-input:focus-within/);
  assert.match(manager, /<span>Name<\/span><input/);
  assert.match(manager, /<span>Extra price<\/span><span className="money-input"><b>\$<\/b><input inputMode="decimal" min="0" placeholder="0\.00"/);
  assert.match(money, /dollarsToCents/);
});

test("native control semantics and specialized portal controls remain intact", async () => {
  const [css, products, scheduling, communications] = await Promise.all([
    source("../../src/style.css"),
    source("../../src/admin/ProductsPage.jsx"),
    source("../../src/admin/SchedulingPage.jsx"),
    source("../../src/admin/CommunicationsPage.jsx"),
  ]);

  assert.match(css, /input:not\(\[type="checkbox"\]\):not\(\[type="radio"\]\)/);
  assert.match(css, /Search\/filter fields keep their intentionally integrated container treatment/);
  assert.match(products, /step="0\.01" type="number"/);
  assert.match(products, /<select required value=/);
  assert.match(products, /<textarea rows="3"/);
  assert.match(scheduling, /type="date"/);
  assert.match(scheduling, /type="time"/);
  assert.match(communications, /<textarea maxLength=\{280\}/);
  assert.match(products, /disabled=\{saving\} type="submit"/);
});

test("portal controls remain width-safe on narrow screens", async () => {
  const css = await source("../../src/style.css");

  assert.match(css, /@media \(max-width: 760px\)[\s\S]*?\.modifier-manager,[\s\S]*?max-width: 100%/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*?\.modifier-edit-row, \.modifier-limits \{ grid-template-columns: 1fr; \}/);
});
