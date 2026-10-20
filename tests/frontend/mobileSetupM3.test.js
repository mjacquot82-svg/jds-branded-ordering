import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("owner setup stays inside a 375px viewport", async () => {
  const css = await readFile(new URL("../../src/style.css", import.meta.url), "utf8");
  assert.match(css, /@media \(max-width: 760px\)\{\.admin-products-page \.admin-products-layout\{grid-template-columns:minmax\(0,1fr\)\}/);
  assert.match(css, /@media\(max-width:800px\)\{\.wizard-progress-shell ol\{display:grid;grid-template-columns:repeat\(8,minmax\(0,1fr\)\)/);
  assert.match(css, /@media\(max-width:680px\)\{\.designer-control-group label:has\(> select\)/);
  assert.match(css, /@media\(max-width:480px\)\{\.starter-picker-filters\{grid-template-columns:1fr\}/);
});
