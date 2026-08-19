const MAX_NATIONAL_DIGITS = 10;

export function getCustomerPhoneDigits(value) {
  const digits = String(value ?? "").replace(/\D/g, "");
  const nationalDigits = digits.length > MAX_NATIONAL_DIGITS && digits.startsWith("1")
    ? digits.slice(1)
    : digits;
  return nationalDigits.slice(0, MAX_NATIONAL_DIGITS);
}

export function formatCustomerPhone(value) {
  const digits = getCustomerPhoneDigits(value);
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

export function normalizeCustomerPhone(value) {
  const digits = getCustomerPhoneDigits(value);
  return digits.length === MAX_NATIONAL_DIGITS ? `+1${digits}` : "";
}

export function isCompleteCustomerPhone(value) {
  return getCustomerPhoneDigits(value).length === MAX_NATIONAL_DIGITS;
}
