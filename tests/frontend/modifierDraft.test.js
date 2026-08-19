import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { applySavedModifierGroup, isModifierDraftDirty } from "../../src/admin/modifierDraft.js";

const saved = {
  backendId: 1, name: "Milk", description: "Choose milk", selectionType: "single",
  required: false, minSelections: 0, maxSelections: 1, active: true, sortOrder: 0,
  choices: [
    { draftId: 10, backendId: 10, name: "Whole milk", price: "0.00", active: true },
    { draftId: 11, backendId: 11, name: "Oat", price: "0.85", active: true },
  ],
};
const changed = (updates) => ({ ...saved, ...updates });

test("loaded Modifier category is clean and normalized name edits revert cleanly", () => {
  assert.equal(isModifierDraftDirty(saved, { ...saved }), false);
  assert.equal(isModifierDraftDirty(changed({ name: "Milk choices" }), saved), true);
  assert.equal(isModifierDraftDirty(changed({ name: " Milk " }), saved), false);
});

test("advanced Modifier settings become dirty and semantic restores become clean", () => {
  assert.equal(isModifierDraftDirty(changed({ required: true, minSelections: 1 }), saved), true);
  assert.equal(isModifierDraftDirty(changed({ required: false, minSelections: 9, maxSelections: 8 }), saved), false);
  assert.equal(isModifierDraftDirty(changed({ active: false }), saved), true);
  assert.equal(isModifierDraftDirty(changed({ active: true }), saved), false);
  const multiple = changed({ selectionType: "multiple", minSelections: 1, maxSelections: 3 });
  assert.equal(isModifierDraftDirty(multiple, saved), true);
  assert.equal(isModifierDraftDirty({ ...multiple, selectionType: "single", required: false }, saved), false);
});

test("Modifier option names and prices become dirty and restore semantically", () => {
  const optionName = saved.choices.map((choice) => choice.backendId === 11 ? { ...choice, name: "Oat Milk" } : choice);
  assert.equal(isModifierDraftDirty(changed({ choices: optionName }), saved), true);
  assert.equal(isModifierDraftDirty(changed({ choices: optionName.map((choice) => choice.backendId === 11 ? { ...choice, name: "Oat" } : choice) }), saved), false);
  const optionPrice = saved.choices.map((choice) => choice.backendId === 11 ? { ...choice, price: "0.95" } : choice);
  assert.equal(isModifierDraftDirty(changed({ choices: optionPrice }), saved), true);
  assert.equal(isModifierDraftDirty(changed({ choices: optionPrice.map((choice) => choice.backendId === 11 ? { ...choice, price: "0.85" } : choice) }), saved), false);
  const optionAvailability = saved.choices.map((choice) => choice.backendId === 11 ? { ...choice, active: false } : choice);
  assert.equal(isModifierDraftDirty(changed({ choices: optionAvailability }), saved), true);
  assert.equal(isModifierDraftDirty(changed({ choices: saved.choices }), saved), false);
});

test("adding an unsaved Modifier option is dirty and removing it returns clean", () => {
  const added = changed({ choices: [...saved.choices, { draftId: "new-1", name: "Almond", price: "0.85", active: true }] });
  assert.equal(isModifierDraftDirty(added, saved), true);
  assert.equal(isModifierDraftDirty(changed({ choices: added.choices.slice(0, -1) }), saved), false);
});

test("untouched new Modifier category is clean and meaningful input is dirty", () => {
  const blank = { name: "", description: "", selectionType: "single", required: false, minSelections: 0, maxSelections: 1, active: true, sortOrder: 2, choices: [] };
  assert.equal(isModifierDraftDirty(blank, { ...blank }), false);
  assert.equal(isModifierDraftDirty({ ...blank, name: "Flavours" }, blank), true);
});

test("Modifier editor retains dirty state through failure and clears it only after success", async () => {
  const page = await readFile(new URL("../../src/admin/ModifierManager.jsx", import.meta.url), "utf8");
  assert.match(page, /if \(busyRef\.current\) return/);
  assert.match(page, /const authoritativeDraft = applySavedModifierGroup\(/);
  assert.match(page, /setDraft\(authoritativeDraft\);\s*setSavedDraft\(authoritativeDraft\)/);
  assert.match(page, /catch \(error\) \{[\s\S]*?setDraft\(\(current\)/);
  assert.doesNotMatch(page, /catch \(error\) \{[\s\S]*?setSavedDraft/);
  assert.match(page, /disabled=\{busy \|\| !dirty\}/);
  assert.match(page, /dirty \? "Unsaved changes" : ""/);
});

test("successful Save uses the authoritative quantity setting as its clean baseline", () => {
  const requested = changed({ selectionType: "multiple", maxSelections: 3, allowQuantity: true });
  const response = {
    id: "1", name: "Milk", description: "Choose milk", selection_type: "multiple",
    required: false, min_selections: 0, max_selections: 3, allow_quantity: false,
    active: true, sort_order: 0,
  };
  const authoritative = applySavedModifierGroup(requested, response, requested.choices);

  assert.equal(authoritative.allowQuantity, false);
  assert.equal(isModifierDraftDirty(authoritative, authoritative), false);
  assert.equal(isModifierDraftDirty(requested, authoritative), true);
});

test("Modifier editor protects local, Owner, history, and browser-leave navigation", async () => {
  const page = await readFile(new URL("../../src/admin/ModifierManager.jsx", import.meta.url), "utf8");
  assert.match(page, /requestDraftAction\(onClose\)/);
  assert.match(page, /requestDraftAction\(closeDraft\)/);
  assert.match(page, /requestDraftAction\(\(\) => loadCategory\(category\)\)/);
  assert.match(page, /window\.navigation/);
  assert.match(page, /navigationApi\.traverseTo\(key\)/);
  assert.match(page, /document\.addEventListener\("click", onClick, true\)/);
  assert.match(page, /window\.addEventListener\("beforeunload", beforeUnload\)/);
  assert.match(page, /window\.removeEventListener\("beforeunload", beforeUnload\)/);
  assert.match(page, /<dialog aria-describedby="unsaved-modifier-message" aria-labelledby="unsaved-modifier-title"/);
  assert.match(page, />Stay<\/button>/);
  assert.match(page, />Leave without saving<\/button>/);
});

test("Modifier availability is honestly part of explicit Save and Product immediates stay separate", async () => {
  const [manager, products] = await Promise.all([
    readFile(new URL("../../src/admin/ModifierManager.jsx", import.meta.url), "utf8"),
    readFile(new URL("../../src/admin/ProductsPage.jsx", import.meta.url), "utf8"),
  ]);
  assert.match(manager, /updateModifier\(modifier\.draftId, "active", !modifier\.active\)/);
  assert.match(manager, /updateDraft\("active", event\.target\.checked\)/);
  assert.match(manager, /await onSaveCustomization/);
  assert.match(products, /await setProductAvailability/);
  assert.match(products, /await setLunchSpecial/);
  assert.doesNotMatch(manager, /setProductAvailability|setLunchSpecial|isProductDraftDirty/);
});
