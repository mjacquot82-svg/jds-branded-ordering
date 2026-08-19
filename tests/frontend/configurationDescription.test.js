import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  formatConfigurationDescription,
  groupConfigurationSelections,
} from "../../src/services/configurationDescription.js";

test("configuration descriptions show one category with one option", () => {
  assert.equal(formatConfigurationDescription([{ groupName: "Milk", name: "Oat" }]), "Milk: Oat");
});

test("configuration descriptions show quantity only above one", () => {
  assert.equal(formatConfigurationDescription([{ groupName: "Sugar", name: "Sugar", quantity: 2 }]), "Sugar: Sugar x2");
  assert.equal(formatConfigurationDescription([{ groupName: "Sugar", name: "Sugar", quantity: 1 }]), "Sugar: Sugar");
});

test("configuration descriptions group multiple options under one category", () => {
  assert.equal(
    formatConfigurationDescription([
      { groupName: "Flavour shots", name: "Vanilla" },
      { groupName: "Flavour shots", name: "Caramel" },
    ]),
    "Flavour shots: Vanilla, Caramel"
  );
});

test("configuration descriptions group multiple options with quantities without repeating the category", () => {
  const description = formatConfigurationDescription([
    { groupName: "Flavour shots", name: "Vanilla", quantity: 2 },
    { groupName: "Flavour shots", name: "Caramel", quantity: 1 },
  ]);

  assert.equal(description, "Flavour shots: Vanilla x2, Caramel");
  assert.doesNotMatch(description, /Flavour shots: Vanilla x2, Flavour shots: Caramel/);
});

test("configuration descriptions keep different categories distinct and operationally structured", () => {
  const selections = [
    { group_name: "Milk", option_name: "Oat", quantity: 1 },
    { group_name: "Sugar", option_name: "Sugar", quantity: 2 },
    { group_name: "Flavour shots", option_name: "Vanilla", quantity: 2 },
    { group_name: "Flavour shots", option_name: "Caramel", quantity: 1 },
  ];

  assert.deepEqual(groupConfigurationSelections(selections).map((group) => group.text), [
    "Milk: Oat",
    "Sugar: Sugar x2",
    "Flavour shots: Vanilla x2, Caramel",
  ]);
  assert.equal(
    formatConfigurationDescription(selections),
    "Milk: Oat · Sugar: Sugar x2 · Flavour shots: Vanilla x2, Caramel"
  );
});

test("Cart and exact-config Quick Order share the grouped customer presentation", async () => {
  const [cart, home] = await Promise.all([
    readFile(new URL("../../src/pages/CartPage.jsx", import.meta.url), "utf8"),
    readFile(new URL("../../src/pages/HomePage.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(cart, /formatConfigurationDescription\(item\.options\)/);
  assert.match(cart, /formatConfigurationDescription\(item\.modifiers\)/);
  assert.match(home, /formatConfigurationDescription\(\[/);
  assert.match(home, /groupName: group\.name, name: modifier\.option_name, quantity: modifier\.quantity/);
});
