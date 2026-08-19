const SUPPORTED_CATALOG_VERSION = "1";

export class CatalogAdapterError extends Error {
  constructor(message) {
    super(message);
    this.name = "CatalogAdapterError";
  }
}

function compareByOrder(left, right) {
  return (
    left.sortOrder - right.sortOrder ||
    left.name.localeCompare(right.name) ||
    left.backendId.localeCompare(right.backendId)
  );
}

function requireArray(value, path) {
  if (!Array.isArray(value)) {
    throw new CatalogAdapterError(`${path} must be an array.`);
  }
  return value;
}

function requireString(value, path) {
  if (typeof value !== "string") {
    throw new CatalogAdapterError(`${path} must be a string.`);
  }
  return value;
}

function requireInteger(value, path) {
  if (!Number.isInteger(value)) {
    throw new CatalogAdapterError(`${path} must be an integer.`);
  }
  return value;
}

function centsToDollars(cents) {
  return cents / 100;
}

function adaptModifierOption(option, path) {
  const priceAdjustmentCents = requireInteger(
    option.price_adjustment_cents,
    `${path}.price_adjustment_cents`
  );

  return {
    id: requireString(option.key, `${path}.key`),
    backendId: requireString(option.id, `${path}.id`),
    name: requireString(option.name, `${path}.name`),
    priceDelta: centsToDollars(priceAdjustmentCents),
    priceAdjustmentCents,
    sortOrder: requireInteger(option.sort_order, `${path}.sort_order`),
  };
}

function adaptModifierGroup(group, path) {
  const selectionType = requireString(
    group.selection_type,
    `${path}.selection_type`
  );
  if (selectionType !== "single" && selectionType !== "multiple") {
    throw new CatalogAdapterError(
      `${path}.selection_type must be "single" or "multiple".`
    );
  }

  return {
    id: requireString(group.key, `${path}.key`),
    backendId: requireString(group.id, `${path}.id`),
    name: requireString(group.name, `${path}.name`),
    description: requireString(group.description, `${path}.description`),
    type: selectionType,
    required: Boolean(group.required),
    minSelections: requireInteger(
      group.min_selections,
      `${path}.min_selections`
    ),
    maxSelections: requireInteger(
      group.max_selections,
      `${path}.max_selections`
    ),
    ...(Object.hasOwn(group, "allow_quantity") ? { allowQuantity: Boolean(group.allow_quantity) } : {}),
    sortOrder: requireInteger(group.sort_order, `${path}.sort_order`),
    options: requireArray(group.options, `${path}.options`)
      .map((option, index) =>
        adaptModifierOption(option, `${path}.options[${index}]`)
      )
      .sort(compareByOrder),
  };
}

function adaptSizeGroup(variants, basePriceCents, path) {
  if (!variants.length) {
    return null;
  }

  return {
    id: "size",
    backendId: null,
    name: "Size",
    description: "",
    type: "single",
    required: true,
    minSelections: 1,
    maxSelections: 1,
    sortOrder: -1,
    options: variants
      .map((variant, index) => {
        const variantPath = `${path}[${index}]`;
        const priceCents = requireInteger(
          variant.price_cents,
          `${variantPath}.price_cents`
        );
        return {
          id: requireString(variant.key, `${variantPath}.key`),
          backendId: requireString(variant.id, `${variantPath}.id`),
          variantId: requireString(variant.id, `${variantPath}.id`),
          name: requireString(variant.name, `${variantPath}.name`),
          priceDelta: centsToDollars(priceCents - basePriceCents),
          priceAdjustmentCents: priceCents - basePriceCents,
          priceCents,
          sortOrder: requireInteger(
            variant.sort_order,
            `${variantPath}.sort_order`
          ),
        };
      })
      .sort(compareByOrder),
  };
}

function adaptProduct(product, category, path) {
  const basePriceCents = requireInteger(
    product.base_price_cents,
    `${path}.base_price_cents`
  );
  const sizeGroup = adaptSizeGroup(
    requireArray(product.variants, `${path}.variants`),
    basePriceCents,
    `${path}.variants`
  );
  const modifierGroups = requireArray(
    product.modifier_groups,
    `${path}.modifier_groups`
  )
    .map((group, index) =>
      adaptModifierGroup(group, `${path}.modifier_groups[${index}]`)
    )
    .sort(compareByOrder);
  const allGroups = sizeGroup ? [sizeGroup, ...modifierGroups] : modifierGroups;

  return {
    id: requireString(product.slug, `${path}.slug`),
    backendId: requireString(product.id, `${path}.id`),
    slug: product.slug,
    name: requireString(product.name, `${path}.name`),
    description: requireString(product.description, `${path}.description`),
    price: centsToDollars(basePriceCents),
    basePriceCents,
    category: category.id,
    categoryBackendId: category.backendId,
    image: requireString(product.image, `${path}.image`),
    available: true,
    featured: Boolean(product.featured),
    lunchSpecial: Boolean(product.lunch_special),
    sortOrder: requireInteger(product.sort_order, `${path}.sort_order`),
    variants: sizeGroup?.options || [],
    modifierGroupIds: allGroups.map((group) => group.id),
    modifierGroups: allGroups,
  };
}

function registryGroup(group) {
  if (group.id !== "size") {
    return group;
  }

  return {
    ...group,
    options: group.options.map(
      ({ backendId, variantId, priceCents, ...option }) => option
    ),
  };
}

export function adaptCatalog(payload) {
  if (!payload || typeof payload !== "object") {
    throw new CatalogAdapterError("Catalog payload must be an object.");
  }
  if (payload.version !== SUPPORTED_CATALOG_VERSION) {
    throw new CatalogAdapterError(
      `Unsupported catalog version: ${String(payload.version)}.`
    );
  }

  const modifierRegistry = new Map();
  const products = [];
  const categories = requireArray(payload.categories, "categories")
    .map((category, categoryIndex) => {
      const path = `categories[${categoryIndex}]`;
      const adaptedCategory = {
        id: requireString(category.slug, `${path}.slug`),
        backendId: requireString(category.id, `${path}.id`),
        slug: category.slug,
        name: requireString(category.name, `${path}.name`),
        note: requireString(category.note, `${path}.note`),
        sortOrder: requireInteger(category.sort_order, `${path}.sort_order`),
      };
      const categoryProducts = requireArray(
        category.products,
        `${path}.products`
      )
        .map((product, productIndex) =>
          adaptProduct(
            product,
            adaptedCategory,
            `${path}.products[${productIndex}]`
          )
        )
        .sort(compareByOrder);

      for (const product of categoryProducts) {
        products.push(product);
        for (const group of product.modifierGroups) {
          if (!modifierRegistry.has(group.id)) {
            modifierRegistry.set(group.id, registryGroup(group));
          }
        }
      }

      return { ...adaptedCategory, products: categoryProducts };
    })
    .sort(compareByOrder);

  return {
    version: payload.version,
    generatedAt: requireString(payload.generated_at, "generated_at"),
    pricing: {
      taxName: requireString(payload.pricing?.tax_name, "pricing.tax_name"),
      taxRateMillionths: requireInteger(
        payload.pricing?.tax_rate_millionths,
        "pricing.tax_rate_millionths"
      ),
    },
    categories,
    products: products.sort(compareByOrder),
    modifierGroups: [...modifierRegistry.values()].sort(compareByOrder),
  };
}
