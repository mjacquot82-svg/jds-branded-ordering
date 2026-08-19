function parseConfiguredSelections(item, productId) {
  const prefix = `${productId}__`;
  if (typeof item.id !== "string" || !item.id.startsWith(prefix)) {
    return new Map();
  }

  return item.id
    .slice(prefix.length)
    .split("|")
    .filter(Boolean)
    .reduce((selections, signature) => {
      const separator = signature.indexOf(":");
      if (separator === -1) {
        return selections;
      }

      const groupId = signature.slice(0, separator);
      const remainder = signature.slice(separator + 1);
      const quantitySeparator = remainder.lastIndexOf(":");
      const optionId = quantitySeparator === -1 ? remainder : remainder.slice(0, quantitySeparator);
      const quantity = quantitySeparator === -1 ? 1 : Number(remainder.slice(quantitySeparator + 1));
      const selectedOptions = selections.get(groupId) || [];
      selectedOptions.push({ optionId, quantity: Number.isSafeInteger(quantity) && quantity > 0 ? quantity : 1 });
      selections.set(groupId, selectedOptions);
      return selections;
    }, new Map());
}

function getProductId(item) {
  if (typeof item.productId === "string" && item.productId) {
    return item.productId;
  }

  return typeof item.id === "string" ? item.id.split("__", 1)[0] : "";
}

function getPriceAdjustmentCents(option) {
  return Number.isInteger(option.priceAdjustmentCents)
    ? option.priceAdjustmentCents
    : Math.round((Number(option.priceDelta) || 0) * 100);
}

function resolveSelections(product, selections) {
  const issues = [];
  const options = [];

  for (const [groupId] of selections) {
    if (!product.modifierGroups.some((group) => group.id === groupId)) {
      issues.push("A selected customization is no longer offered.");
    }
  }

  for (const group of product.modifierGroups) {
    const selectedEntries = selections.get(group.id) || [];
    const selectedIds = selectedEntries.map((entry) => typeof entry === "string" ? entry : entry.optionId);
    const selectedOptions = group.options.filter((option) =>
      selectedIds.includes(option.id)
    );

    if (selectedOptions.length !== selectedIds.length) {
      issues.push(`${group.name} has changed.`);
    }
    if (group.type === "single" && selectedIds.length > 1) {
      issues.push(`${group.name} must have one selection.`);
    }

    const totalQuantity = selectedEntries.reduce((sum, entry) => sum + (typeof entry === "string" ? 1 : entry.quantity), 0);
    const minimum = group.required ? Math.max(1, group.minSelections || 0) : group.minSelections || 0;
    if (!group.allowQuantity && selectedEntries.some((entry) => typeof entry !== "string" && entry.quantity !== 1)) {
      issues.push(`${group.name} does not allow quantities.`);
    }
    if (totalQuantity < minimum) {
      issues.push(`${group.name} needs a selection.`);
    }
    if (group.maxSelections > 0 && totalQuantity > group.maxSelections) {
      issues.push(`${group.name} has too many selections.`);
    }

    options.push(
      ...selectedOptions.map((option) => ({
        groupId: group.id,
        groupBackendId: group.backendId,
        groupName: group.name,
        id: option.id,
        backendId: option.backendId,
        variantId: option.variantId,
        name: option.name,
        priceDelta: getPriceAdjustmentCents(option) / 100,
        priceAdjustmentCents: getPriceAdjustmentCents(option),
        quantity: selectedEntries.find((entry) => (typeof entry === "string" ? entry : entry.optionId) === option.id)?.quantity || 1,
      }))
    );
  }

  return { issues: [...new Set(issues)], options };
}

export function resolveCart(catalog, cart) {
  const products = catalog?.products || [];
  const productsById = new Map(products.map((product) => [product.id, product]));

  const lines = cart.map((item) => {
    const productId = getProductId(item);
    const product = productsById.get(productId);

    if (!product) {
      return {
        ...item,
        productId,
        resolution: "unavailable",
        issues: ["This item is no longer on the current menu."],
      };
    }

    const selections = parseConfiguredSelections(item, productId);
    const { issues, options } = resolveSelections(product, selections);
    const priceCents =
      product.basePriceCents +
      options.reduce((sum, option) => sum + option.priceAdjustmentCents * option.quantity, 0);

    if (issues.length) {
      return {
        ...item,
        productId,
        productBackendId: product.backendId,
        resolution: "reconfigure",
        issues,
      };
    }

    return {
      ...item,
      productId,
      productBackendId: product.backendId,
      name: product.name,
      description: product.description,
      basePrice: product.basePriceCents / 100,
      basePriceCents: product.basePriceCents,
      price: priceCents / 100,
      priceCents,
      options,
      resolution: "ready",
      issues: [],
    };
  });

  const totalCents = lines.reduce(
    (sum, line) =>
      line.resolution === "ready" ? sum + line.priceCents * line.quantity : sum,
    0
  );

  return {
    lines,
    total: totalCents / 100,
    totalCents,
    hasStaleLines: lines.some((line) => line.resolution !== "ready"),
  };
}
