import { dollarsToCents } from "../services/modifierMoney.js";

export function validateModifierDraft(draft) {
  const errors = { choices: {} };
  if (!draft.name.trim()) errors.groupName = "Enter a modifier category name.";
  const choices = [];
  for (const choice of draft.choices) {
    const choiceErrors = {};
    if (!choice.name.trim()) choiceErrors.name = "Enter a modifier name.";
    const cents = dollarsToCents(choice.price);
    if (cents === null) choiceErrors.price = "Enter a valid extra price, such as 0.25.";
    if (Object.keys(choiceErrors).length) errors.choices[choice.draftId] = choiceErrors;
    else choices.push({ ...choice, priceAdjustmentCents: cents });
  }
  if ((draft.selectionType === "multiple" || draft.allowQuantity) && Number(draft.maxSelections) && Number(draft.maxSelections) < Number(draft.minSelections)) {
    errors.advanced = "Maximum selections cannot be less than minimum selections.";
  }
  if (!Number.isInteger(Number(draft.minSelections)) || Number(draft.minSelections) < 0 || !Number.isInteger(Number(draft.maxSelections)) || Number(draft.maxSelections) < 0) {
    errors.advanced = "Selection limits must be whole numbers of zero or more.";
  }
  return { choices, errors, valid: !(errors.groupName || errors.advanced || Object.keys(errors.choices).length) };
}
