import assert from "node:assert/strict";
import test from "node:test";

import {
  CatalogAdapterError,
  adaptCatalog,
} from "../../src/services/catalogAdapter.js";

function catalogFixture() {
  return {
    version: "1",
    generated_at: "2026-07-27T12:00:00Z",
    pricing: { tax_name: "HST", tax_rate_millionths: 1_300_000 },
    categories: [
      {
        id: "20",
        slug: "iced-drinks",
        name: "Iced Drinks",
        note: "Cool café pours.",
        sort_order: 3,
        products: [
          {
            id: "200",
            slug: "cold-brew",
            name: "Cold Brew",
            description: "Slow-steeped and poured over ice.",
            image: "coffee",
            featured: true,
            lunch_special: true,
            base_price_cents: 475,
            sort_order: 1,
            variants: [
              {
                id: "2003",
                key: "large",
                name: "Large",
                price_cents: 600,
                sort_order: 2,
              },
              {
                id: "2001",
                key: "small",
                name: "Small",
                price_cents: 475,
                sort_order: 0,
              },
              {
                id: "2002",
                key: "medium",
                name: "Medium",
                price_cents: 550,
                sort_order: 1,
              },
            ],
            modifier_groups: [
              {
                id: "302",
                key: "flavour-shots",
                name: "Flavour shots",
                description: "",
                selection_type: "multiple",
                required: false,
                min_selections: 0,
                max_selections: 0,
                sort_order: 1,
                options: [
                  {
                    id: "3022",
                    key: "caramel",
                    name: "Caramel",
                    price_adjustment_cents: 75,
                    sort_order: 1,
                  },
                  {
                    id: "3021",
                    key: "vanilla",
                    name: "Vanilla",
                    price_adjustment_cents: 75,
                    sort_order: 0,
                  },
                ],
              },
              {
                id: "301",
                key: "milk",
                name: "Milk",
                description: "",
                selection_type: "single",
                required: false,
                min_selections: 0,
                max_selections: 1,
                sort_order: 0,
                options: [
                  {
                    id: "3011",
                    key: "whole",
                    name: "Whole milk",
                    price_adjustment_cents: 0,
                    sort_order: 0,
                  },
                  {
                    id: "3012",
                    key: "oat",
                    name: "Oat",
                    price_adjustment_cents: 85,
                    sort_order: 1,
                  },
                ],
              },
            ],
          },
        ],
      },
      {
        id: "10",
        slug: "coffee",
        name: "Coffee",
        note: "House cups.",
        sort_order: 0,
        products: [
          {
            id: "100",
            slug: "drip-coffee",
            name: "Drip Coffee",
            description: "Warm and steady.",
            image: "coffee",
            featured: true,
            lunch_special: false,
            base_price_cents: 375,
            sort_order: 0,
            variants: [],
            modifier_groups: [],
          },
        ],
      },
    ],
  };
}

test("adaptCatalog preserves the legacy category and product interfaces", () => {
  const source = catalogFixture();
  const sourceSnapshot = structuredClone(source);
  const result = adaptCatalog(source);

  assert.deepEqual(source, sourceSnapshot, "adapter must not mutate the API payload");
  assert.equal(result.version, "1");
  assert.equal(result.generatedAt, source.generated_at);
  assert.deepEqual(result.pricing, {
    taxName: "HST",
    taxRateMillionths: 1_300_000,
  });
  assert.deepEqual(
    result.categories.map(({ id, backendId, name, note, sortOrder }) => ({
      id,
      backendId,
      name,
      note,
      sortOrder,
    })),
    [
      {
        id: "coffee",
        backendId: "10",
        name: "Coffee",
        note: "House cups.",
        sortOrder: 0,
      },
      {
        id: "iced-drinks",
        backendId: "20",
        name: "Iced Drinks",
        note: "Cool café pours.",
        sortOrder: 3,
      },
    ]
  );

  assert.deepEqual(result.products.map((product) => product.id), [
    "drip-coffee",
    "cold-brew",
  ]);

  const coldBrew = result.products[1];
  assert.deepEqual(
    {
      id: coldBrew.id,
      backendId: coldBrew.backendId,
      name: coldBrew.name,
      description: coldBrew.description,
      price: coldBrew.price,
      basePriceCents: coldBrew.basePriceCents,
      category: coldBrew.category,
      categoryBackendId: coldBrew.categoryBackendId,
      image: coldBrew.image,
      available: coldBrew.available,
      featured: coldBrew.featured,
      lunchSpecial: coldBrew.lunchSpecial,
      modifierGroupIds: coldBrew.modifierGroupIds,
    },
    {
      id: "cold-brew",
      backendId: "200",
      name: "Cold Brew",
      description: "Slow-steeped and poured over ice.",
      price: 4.75,
      basePriceCents: 475,
      category: "iced-drinks",
      categoryBackendId: "20",
      image: "coffee",
      available: true,
      featured: true,
      lunchSpecial: true,
      modifierGroupIds: ["size", "milk", "flavour-shots"],
    }
  );
  assert.equal(result.categories[1].products[0], coldBrew);
});

test("adaptCatalog maps variants to an ordered legacy Size group", () => {
  const coldBrew = adaptCatalog(catalogFixture()).products[1];
  const size = coldBrew.modifierGroups[0];

  assert.deepEqual(
    {
      id: size.id,
      name: size.name,
      type: size.type,
      required: size.required,
      minSelections: size.minSelections,
      maxSelections: size.maxSelections,
    },
    {
      id: "size",
      name: "Size",
      type: "single",
      required: true,
      minSelections: 1,
      maxSelections: 1,
    }
  );
  assert.deepEqual(
    size.options.map(
      ({
        id,
        backendId,
        variantId,
        priceDelta,
        priceAdjustmentCents,
        priceCents,
      }) => ({
        id,
        backendId,
        variantId,
        priceDelta,
        priceAdjustmentCents,
        priceCents,
      })
    ),
    [
      {
        id: "small",
        backendId: "2001",
        variantId: "2001",
        priceDelta: 0,
        priceAdjustmentCents: 0,
        priceCents: 475,
      },
      {
        id: "medium",
        backendId: "2002",
        variantId: "2002",
        priceDelta: 0.75,
        priceAdjustmentCents: 75,
        priceCents: 550,
      },
      {
        id: "large",
        backendId: "2003",
        variantId: "2003",
        priceDelta: 1.25,
        priceAdjustmentCents: 125,
        priceCents: 600,
      },
    ]
  );
});

test("adaptCatalog maps and orders modifier groups and options", () => {
  const result = adaptCatalog(catalogFixture());
  const coldBrew = result.products[1];

  assert.deepEqual(
    coldBrew.modifierGroups.map((group) => group.id),
    ["size", "milk", "flavour-shots"]
  );
  assert.deepEqual(
    coldBrew.modifierGroups[1],
    {
      id: "milk",
      backendId: "301",
      name: "Milk",
      description: "",
      type: "single",
      required: false,
      minSelections: 0,
      maxSelections: 1,
      sortOrder: 0,
      options: [
        {
          id: "whole",
          backendId: "3011",
          name: "Whole milk",
          priceDelta: 0,
          priceAdjustmentCents: 0,
          sortOrder: 0,
        },
        {
          id: "oat",
          backendId: "3012",
          name: "Oat",
          priceDelta: 0.85,
          priceAdjustmentCents: 85,
          sortOrder: 1,
        },
      ],
    }
  );
  assert.deepEqual(result.modifierGroups.map((group) => group.id), [
    "size",
    "milk",
    "flavour-shots",
  ]);
});

test("adaptCatalog rejects unsupported or malformed contracts", () => {
  assert.throws(
    () => adaptCatalog({ ...catalogFixture(), version: "2" }),
    (error) =>
      error instanceof CatalogAdapterError &&
      error.message === "Unsupported catalog version: 2."
  );

  const malformed = catalogFixture();
  malformed.categories[0].products[0].base_price_cents = 4.75;
  assert.throws(
    () => adaptCatalog(malformed),
    /base_price_cents must be an integer/
  );
});
