export function getModifierGroupsForProduct(product) {
  return product.modifierGroups || [];
}

export function getProductSpecificImageUrl(product) {
  const image = product?.image?.trim();

  if (!image) {
    return "";
  }

  return /^(https?:\/\/|data:image\/|blob:|\.?\.?\/)/i.test(image) ? image : "";
}

export function getProductChoicePresentation(product) {
  const groups = getModifierGroupsForProduct(product);

  if (!groups.length) {
    return "direct";
  }

  const [group] = groups;
  return groups.length === 1 && group.type === "single" && group.options.length <= 4
    ? "simple"
    : "complex";
}

export function getCategoryById(categories, categoryId) {
  return categories.find((category) => category.id === categoryId);
}

export function resolveMenuCategory(sections, categorySlug, targetProduct) {
  const requestedCategory = targetProduct?.category || categorySlug;

  return sections.some((section) => section.id === requestedCategory)
    ? requestedCategory
    : sections[0]?.id || "";
}

export function getDefaultSelections(product, { selectRequired = false } = {}) {
  return getModifierGroupsForProduct(product).reduce((selections, group) => {
    return {
      ...selections,
      [group.id]: selectRequired && group.required && group.options[0]
        ? (group.allowQuantity ? { [group.options[0].id]: 1 } : group.type === "multiple" ? [group.options[0].id] : group.options[0].id)
        : group.allowQuantity ? {} : group.type === "multiple" ? [] : "",
    };
  }, {});
}

export function getMissingRequiredChoice(product, selections) {
  return getModifierGroupsForProduct(product).find((group) => {
    const selectedValue = selections[group.id];
    if (selectedValue === "__none__") return group.required;
    const selectedCount = group.allowQuantity
      ? Object.values(selectedValue || {}).reduce((sum, quantity) => sum + quantity, 0)
      : Array.isArray(selectedValue)
      ? selectedValue.length
      : selectedValue
        ? 1
        : 0;
    const minimum = group.required ? Math.max(1, group.minSelections || 0) : group.minSelections || 0;
    const distinctCount = group.allowQuantity
      ? Object.values(selectedValue || {}).filter((quantity) => quantity > 0).length
      : Array.isArray(selectedValue) ? selectedValue.length : selectedValue ? 1 : 0;
    return (group.type === "single" && distinctCount > 1) || selectedCount < minimum || (group.maxSelections > 0 && selectedCount > group.maxSelections) || selectedCount === 0;
  });
}

export function resolveQuickConfigurationSelections(product, configuration) {
  if (!product?.available || !configuration || !Array.isArray(configuration.modifiers)) {
    return null;
  }

  const groups = getModifierGroupsForProduct(product);
  const sizeGroup = groups.find((group) => group.id === "size");
  const selections = {};
  if (sizeGroup) {
    const variant = sizeGroup.options.find(
      (option) => option.backendId === configuration.variant_id
    );
    if (!variant) return null;
    selections[sizeGroup.id] = variant.id;
  } else if (configuration.variant_id != null) {
    return null;
  }

  const configuredByGroup = new Map();
  const seenOptionIds = new Set();
  for (const modifier of configuration.modifiers) {
    if (
      !modifier
      || seenOptionIds.has(modifier.option_id)
      || !Number.isInteger(modifier.quantity)
      || modifier.quantity < 1
    ) {
      return null;
    }
    const matchingGroups = groups.filter(
      (group) => group.id !== "size"
        && group.options.some((option) => option.backendId === modifier.option_id)
    );
    if (matchingGroups.length !== 1) return null;
    const group = matchingGroups[0];
    const option = group.options.find(
      (candidate) => candidate.backendId === modifier.option_id
    );
    seenOptionIds.add(modifier.option_id);
    configuredByGroup.set(group.id, [
      ...(configuredByGroup.get(group.id) || []),
      { option, quantity: modifier.quantity },
    ]);
  }

  for (const group of groups.filter((candidate) => candidate.id !== "size")) {
    const configured = configuredByGroup.get(group.id) || [];
    const selectedCount = configured.reduce(
      (total, selection) => total + selection.quantity,
      0
    );
    const minimum = group.required
      ? Math.max(1, group.minSelections || 0)
      : group.minSelections || 0;
    if (
      (group.type === "single" && configured.length > 1)
      || (!group.allowQuantity && configured.some((selection) => selection.quantity !== 1))
      || selectedCount < minimum
      || (group.maxSelections > 0 && selectedCount > group.maxSelections)
    ) {
      return null;
    }
    selections[group.id] = group.allowQuantity
      ? Object.fromEntries(configured.map(({ option, quantity }) => [option.id, quantity]))
      : group.type === "multiple"
        ? configured.map(({ option }) => option.id)
        : configured[0]?.option.id || "__none__";
  }

  return selections;
}

export function getSelectedOptions(product, selections) {
  return getModifierGroupsForProduct(product).flatMap((group) => {
    const selectedValue = selections[group.id];
    const selectedIds = group.allowQuantity
      ? Object.keys(selectedValue || {}).filter((id) => selectedValue[id] > 0)
      : Array.isArray(selectedValue)
      ? selectedValue
      : [selectedValue];

    return selectedIds
      .map((optionId) => {
        const option = group.options.find((item) => item.id === optionId);
        return option
          ? { groupId: group.id, groupName: group.name, quantity: group.allowQuantity ? selectedValue[optionId] : 1, ...option }
          : null;
      })
      .filter(Boolean);
  });
}

export function getConfiguredPrice(product, selections) {
  return getSelectedOptions(product, selections).reduce(
    (sum, option) => sum + (Number(option.priceDelta) || 0) * (option.quantity || 1),
    product.price
  );
}

export function getCartLineId(product, selectedOptions) {
  const optionSignature = selectedOptions
    .map((option) => `${option.groupId}:${option.id}${(option.quantity || 1) > 1 ? `:${option.quantity}` : ""}`)
    .sort()
    .join("|");

  return optionSignature
    ? `${product.id}__${optionSignature}`
    : product.id;
}

export function groupProductsByCategory(categories, products) {
  return categories
    .map((category) => ({
      ...category,
      items: products.filter(
        (product) =>
          product.category === category.id && product.available
      ),
    }))
    .filter((section) => section.items.length);
}
