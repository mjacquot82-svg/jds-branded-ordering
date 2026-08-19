import assert from "node:assert/strict";
import test from "node:test";

import { resolveCart } from "../../src/services/cartCatalog.js";

function catalogWithLatte() {
  return {
    products: [
      {
        id: "latte",
        backendId: "product-1",
        name: "Latte",
        description: "Espresso with steamed milk.",
        basePriceCents: 525,
        modifierGroups: [
          {
            id: "size",
            backendId: null,
            name: "Size",
            type: "single",
            required: true,
            minSelections: 1,
            maxSelections: 1,
            options: [
              {
                id: "small",
                backendId: "variant-1",
                variantId: "variant-1",
                name: "Small",
                priceAdjustmentCents: 0,
              },
              {
                id: "large",
                backendId: "variant-2",
                variantId: "variant-2",
                name: "Large",
                priceAdjustmentCents: 125,
              },
            ],
          },
          {
            id: "milk",
            backendId: "group-1",
            name: "Milk",
            type: "single",
            required: false,
            minSelections: 0,
            maxSelections: 1,
            options: [
              {
                id: "oat",
                backendId: "option-1",
                name: "Oat",
                priceAdjustmentCents: 85,
              },
            ],
          },
          {
            id: "flavour-shots",
            backendId: "group-2",
            name: "Flavour shots",
            type: "multiple",
            required: false,
            minSelections: 0,
            maxSelections: 0,
            options: [
              {
                id: "vanilla",
                backendId: "option-2",
                name: "Vanilla",
                priceAdjustmentCents: 75,
              },
              {
                id: "caramel",
                backendId: "option-3",
                name: "Caramel",
                priceAdjustmentCents: 75,
              },
            ],
          },
        ],
      },
    ],
  };
}

function configuredLatte(overrides = {}) {
  return {
    id: "latte__flavour-shots:caramel|flavour-shots:vanilla|milk:oat|size:large",
    productId: "latte",
    name: "Latte",
    description: "Saved description.",
    basePrice: 5.25,
    price: 8.85,
    quantity: 2,
    options: [
      { groupName: "Size", name: "Large", priceDelta: 1.25 },
      { groupName: "Milk", name: "Oat", priceDelta: 0.85 },
      { groupName: "Flavour shots", name: "Vanilla", priceDelta: 0.75 },
      { groupName: "Flavour shots", name: "Caramel", priceDelta: 0.75 },
    ],
    ...overrides,
  };
}

test("Cart resolves existing configured lines and recalculates production pricing", () => {
  const result = resolveCart(catalogWithLatte(), [configuredLatte({ price: 999 })]);
  const [line] = result.lines;

  assert.equal(line.resolution, "ready");
  assert.equal(line.productBackendId, "product-1");
  assert.equal(line.priceCents, 885);
  assert.equal(line.price, 8.85);
  assert.equal(result.totalCents, 1770);
  assert.equal(result.total, 17.7);
  assert.equal(result.hasStaleLines, false);
});

test("Cart resolves variants and modifiers to opaque backend identifiers", () => {
  const [line] = resolveCart(catalogWithLatte(), [configuredLatte()]).lines;

  assert.deepEqual(
    line.options.map(({ groupId, id, backendId, variantId }) => ({
      groupId,
      id,
      backendId,
      variantId,
    })),
    [
      {
        groupId: "size",
        id: "large",
        backendId: "variant-2",
        variantId: "variant-2",
      },
      {
        groupId: "milk",
        id: "oat",
        backendId: "option-1",
        variantId: undefined,
      },
      {
        groupId: "flavour-shots",
        id: "vanilla",
        backendId: "option-2",
        variantId: undefined,
      },
      {
        groupId: "flavour-shots",
        id: "caramel",
        backendId: "option-3",
        variantId: undefined,
      },
    ]
  );
});

test("Cart retains removed or unpublished product snapshots as unavailable", () => {
  const original = configuredLatte();
  const result = resolveCart({ products: [] }, [original]);

  assert.equal(result.lines[0].resolution, "unavailable");
  assert.equal(result.lines[0].name, original.name);
  assert.match(result.lines[0].issues[0], /no longer/);
  assert.equal(result.totalCents, 0);
  assert.equal(result.hasStaleLines, true);
});

test("Cart marks removed variants or modifier options for reconfiguration", () => {
  const catalog = catalogWithLatte();
  catalog.products[0].modifierGroups[0].options =
    catalog.products[0].modifierGroups[0].options.filter(
      (option) => option.id !== "large"
    );
  catalog.products[0].modifierGroups[1].options = [];

  const result = resolveCart(catalog, [configuredLatte()]);

  assert.equal(result.lines[0].resolution, "reconfigure");
  assert.match(result.lines[0].issues.join(" "), /Size has changed/);
  assert.match(result.lines[0].issues.join(" "), /Milk has changed/);
  assert.equal(result.totalCents, 0);
});

test("Cart marks newly required selections for reconfiguration", () => {
  const catalog = catalogWithLatte();
  catalog.products[0].modifierGroups[1].required = true;
  catalog.products[0].modifierGroups[1].minSelections = 1;
  const item = configuredLatte({
    id: "latte__size:small",
    options: [{ groupName: "Size", name: "Small", priceDelta: 0 }],
  });

  const result = resolveCart(catalog, [item]);

  assert.equal(result.lines[0].resolution, "reconfigure");
  assert.match(result.lines[0].issues.join(" "), /Milk needs a selection/);
});

test("Cart supports legacy entries whose product slug is inferred from the line id", () => {
  const item = configuredLatte();
  delete item.productId;

  const result = resolveCart(catalogWithLatte(), [item]);

  assert.equal(result.lines[0].resolution, "ready");
  assert.equal(result.lines[0].productId, "latte");
});
