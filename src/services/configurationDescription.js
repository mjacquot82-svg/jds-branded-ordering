function groupName(selection) {
  return selection.groupName ?? selection.group_name ?? "Modifier";
}

function optionName(selection) {
  return selection.name ?? selection.option_name ?? "";
}

function optionDescription(selection) {
  const quantity = Number(selection.quantity) || 1;
  return `${optionName(selection)}${quantity > 1 ? ` x${quantity}` : ""}`;
}

export function groupConfigurationSelections(selections = []) {
  const groups = new Map();

  for (const selection of selections) {
    const name = groupName(selection);
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(optionDescription(selection));
  }

  return [...groups].map(([name, options]) => ({
    name,
    options,
    text: `${name}: ${options.join(", ")}`,
  }));
}

export function formatConfigurationDescription(selections = [], separator = " · ") {
  return groupConfigurationSelections(selections).map((group) => group.text).join(separator);
}
