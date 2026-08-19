import assert from "node:assert/strict";
import { after, test } from "node:test";

import { JSDOM } from "jsdom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const vite = await createServer({ appType: "custom", server: { hmr: false, middlewareMode: true } });
const [{ default: ModifierManager }, { toOwnerCustomizationWrite }] = await Promise.all([
  vite.ssrLoadModule("/src/admin/ModifierManager.jsx"),
  vite.ssrLoadModule("/src/services/modifierMoney.js"),
]);

after(() => vite.close());

const group = (name, allowQuantity = false, selectionType = allowQuantity ? "multiple" : "single") => ({
  id: name.toLowerCase().replaceAll(" ", "-"),
  backendId: `group-${name.toLowerCase().replaceAll(" ", "-")}`,
  name,
  description: "",
  selectionType,
  required: false,
  minSelections: 0,
  maxSelections: allowQuantity ? 3 : 1,
  allowQuantity,
  active: true,
  sortOrder: 0,
  assignmentCount: 1,
  options: [{ id: "option", backendId: "91", name: name === "Milk" ? "Oat" : name, priceAdjustmentCents: 0, active: true, sortOrder: 0 }],
});

async function renderManager({ groups = [], onSaveCustomization = async () => {} } = {}) {
  const dom = new JSDOM("<!doctype html><html><body><div id=\"root\"></div></body></html>", { url: "https://cafe.test/admin/products" });
  const previous = { document: globalThis.document, navigator: globalThis.navigator, window: globalThis.window };
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
  dom.window.HTMLDialogElement.prototype.showModal = function showModal() { this.open = true; };
  dom.window.HTMLDialogElement.prototype.close = function close() { this.open = false; };
  const root = createRoot(document.getElementById("root"));
  await act(async () => root.render(React.createElement(
    MemoryRouter,
    null,
    React.createElement(ModifierManager, { groups, onClose() {}, onSaveCustomization }),
  )));
  return {
    dom,
    root,
    async cleanup() {
      await act(async () => root.unmount());
      dom.window.close();
      globalThis.window = previous.window;
      globalThis.document = previous.document;
      Object.defineProperty(globalThis, "navigator", { configurable: true, value: previous.navigator });
    },
  };
}

async function click(element, dom) {
  assert.ok(element);
  await act(async () => element.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true })));
}

const button = (label) => [...document.querySelectorAll("button")].find((item) => item.textContent.trim() === label);
const quantityInput = () => [...document.querySelectorAll('input[type="checkbox"]')].find((input) => input.closest("label")?.textContent.includes("Allow quantities"));

test("actual Modifier Edit UI independently composes all selection and quantity modes", { concurrency: false }, async () => {
  const app = await renderManager({ groups: [group("Generic one"), group("Generic multiple quantity", true), group("Generic one quantity", true, "single")] });
  try {
    await click(button("Edit"), app.dom);
    assert.match(document.querySelector(".modifier-editor").textContent, /How can customers choose.*Allow quantities/s);
    assert.equal(quantityInput().checked, false);
    assert.equal(quantityInput().disabled, false);
    await click(quantityInput(), app.dom);
    assert.equal(quantityInput().checked, true);
    assert.equal([...document.querySelectorAll("label")].find((item) => item.textContent.includes("One option")).querySelector("input").checked, true);
    assert.match(document.querySelector(".modifier-save-actions").textContent, /Unsaved changes/);
    await click(quantityInput(), app.dom);
    assert.doesNotMatch(document.querySelector(".modifier-save-actions").textContent, /Unsaved changes/);

    await click(button("Back to modifiers"), app.dom);
    await click([...document.querySelectorAll(".modifier-category header button")][1], app.dom);
    assert.equal(document.querySelector(".modifier-editor h2").textContent, "Generic multiple quantity");
    assert.equal(quantityInput().checked, true);
    assert.equal([...document.querySelectorAll("label")].find((item) => item.textContent.includes("Multiple options")).querySelector("input").checked, true);
    await click(quantityInput(), app.dom);
    assert.equal(quantityInput().checked, false);
    assert.match(document.querySelector(".modifier-save-actions").textContent, /Unsaved changes/);
    await click(quantityInput(), app.dom);
    assert.doesNotMatch(document.querySelector(".modifier-save-actions").textContent, /Unsaved changes/);
    await click(button("Back to modifiers"), app.dom);
    await click([...document.querySelectorAll(".modifier-category header button")][2], app.dom);
    assert.equal(quantityInput().checked, true);
    assert.equal([...document.querySelectorAll("label")].find((item) => item.textContent.includes("One option")).querySelector("input").checked, true);
    assert.equal(document.querySelectorAll(".modifier-editor").length, 1);
  } finally { await app.cleanup(); }
});

test("actual Modifier Create UI exposes quantity and failed Edit Save preserves the draft and leave guard", { concurrency: false }, async () => {
  const app = await renderManager({
    groups: [group("Flavour shots", true)],
    onSaveCustomization: async () => { throw new Error("Temporary save failure."); },
  });
  try {
    await click(button("+ Add modifier category"), app.dom);
    assert.match(document.querySelector(".modifier-editor").textContent, /Allow quantities/);
    assert.equal(quantityInput().checked, false);
    assert.equal(quantityInput().disabled, false);
    await click(button("Back to modifiers"), app.dom);
    await click(button("Edit"), app.dom);
    await click(quantityInput(), app.dom);
    await click(button("Save changes"), app.dom);
    assert.match(document.body.textContent, /Temporary save failure/);
    assert.equal(quantityInput().checked, false);
    assert.match(document.querySelector(".modifier-save-actions").textContent, /Unsaved changes/);
    await click(button("Back to modifiers"), app.dom);
    assert.equal(document.querySelector("dialog").open, true);
    assert.match(document.querySelector("dialog").textContent, /Leave without saving/);
  } finally { await app.cleanup(); }
});

test("actual Modifier Edit Save sends quantity and uses each authoritative response as the clean baseline", { concurrency: false }, async () => {
  const requests = [];
  const app = await renderManager({
    groups: [group("Generic group")],
    onSaveCustomization: async (draft) => {
      requests.push(toOwnerCustomizationWrite(draft).group);
      return {
        group: {
          id: "41", name: draft.name, description: "", selection_type: "single", required: false,
          min_selections: 0, max_selections: requests.length === 1 ? 3 : 1, allow_quantity: requests.length === 1,
          active: true, sort_order: 0,
        },
        choices: draft.choices.map((choice) => ({ clientId: choice.draftId, response: { id: choice.backendId } })),
      };
    },
  });
  try {
    await click(button("Edit"), app.dom);
    await click(quantityInput(), app.dom);
    const maximum = [...document.querySelectorAll('input[type="number"]')][0];
    await act(async () => { maximum.value = "3"; maximum.dispatchEvent(new app.dom.window.Event("input", { bubbles: true })); });
    await click(button("Save changes"), app.dom);
    assert.equal(requests[0].allow_quantity, true);
    assert.equal(requests[0].selection_type, "single");
    assert.equal(requests[0].max_selections, 0);
    assert.equal(quantityInput().checked, true);
    assert.doesNotMatch(document.querySelector(".modifier-save-actions").textContent, /Unsaved changes/);

    await click(quantityInput(), app.dom);
    await click(button("Save changes"), app.dom);
    assert.equal(requests[1].allow_quantity, false);
    assert.equal(quantityInput().checked, false);
    assert.doesNotMatch(document.querySelector(".modifier-save-actions").textContent, /Unsaved changes/);
  } finally { await app.cleanup(); }
});
