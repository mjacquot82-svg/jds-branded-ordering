import { OrderApiError } from "./orderApi.js";
import { CloverCheckoutError } from "./cloverService.js";
import { normalizeCustomerPhone } from "./customerPhone.js";

const PENDING_ORDER_SUBMISSION_KEY = "guesthouse-pending-order-submission";

function canonicalize(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonicalize(value[key])])
    );
  }
  return value;
}

function freezeRecursively(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) {
    return value;
  }
  Object.values(value).forEach(freezeRecursively);
  return Object.freeze(value);
}

async function hashPayload(payload, cryptoImpl) {
  const { idempotency_key: _, ...submission } = payload;
  const canonicalPayload = JSON.stringify(canonicalize(submission));
  const digest = await cryptoImpl.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(canonicalPayload)
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("");
}

function requireBackendId(value, field) {
  const numericValue = Number(value);
  if (!Number.isSafeInteger(numericValue) || numericValue <= 0) {
    throw new Error(`${field} is unavailable.`);
  }
  return numericValue;
}

export function buildPendingOrderRequest({
  contact,
  idempotencyKey,
  lines,
  notes,
  requestedPickupAt,
}) {
  return {
    idempotency_key: idempotencyKey,
    customer: canonicalizeCheckoutContact(contact),
    requested_pickup_at: requestedPickupAt,
    notes: notes.trim() || null,
    lines: lines.map((line) => {
      const variant = line.options.find((option) => option.variantId);
      return {
        product_id: requireBackendId(
          line.productBackendId,
          `${line.name} product`
        ),
        variant_id: variant
          ? requireBackendId(variant.variantId, `${line.name} variant`)
          : null,
        modifier_selections: line.options
          .filter((option) => !option.variantId)
          .map((option) =>
            ({ modifier_option_id: requireBackendId(option.backendId, `${line.name} modifier`), quantity: option.quantity || 1 })
          ),
        quantity: line.quantity,
      };
    }),
  };
}

export function canonicalizeCheckoutContact(contact = {}) {
  return {
    name: String(contact.name || "").trim(),
    email: String(contact.email || "").trim(),
    phone: normalizeCustomerPhone(contact.phone),
  };
}

export function resolveVisibleCheckoutContact(stateContact = {}, inputContact = {}) {
  return canonicalizeCheckoutContact({
    name: typeof inputContact.name === "string" ? inputContact.name : stateContact.name,
    email: typeof inputContact.email === "string" ? inputContact.email : stateContact.email,
    phone: typeof inputContact.phone === "string" ? inputContact.phone : stateContact.phone,
  });
}

export function isCheckoutContactComplete(contact) {
  const canonical = canonicalizeCheckoutContact(contact);
  return Boolean(
    canonical.name.split(/\s+/).filter(Boolean).length >= 2
    && canonical.email
    && canonical.phone
  );
}

export function formatPickupTimeInput(requestedPickupAt, timeZone) {
  if (!requestedPickupAt || !timeZone) return "";

  const parts = new Intl.DateTimeFormat("en-CA", {
    hour: "2-digit",
    hourCycle: "h23",
    minute: "2-digit",
    timeZone,
  }).formatToParts(new Date(requestedPickupAt));
  const hour = parts.find((part) => part.type === "hour")?.value;
  const minute = parts.find((part) => part.type === "minute")?.value;
  return hour && minute ? `${hour}:${minute}` : "";
}

export function createSubmissionGate() {
  let inFlight = false;

  return {
    begin() {
      if (inFlight) {
        return false;
      }
      inFlight = true;
      return true;
    },
    end() {
      inFlight = false;
    },
    isInFlight() {
      return inFlight;
    },
  };
}

export async function prepareOrderSubmission(
  payload,
  {
    cryptoImpl = globalThis.crypto,
    fingerprintPayload = payload,
    storage = globalThis.sessionStorage,
  } = {}
) {
  if (
    !cryptoImpl?.subtle ||
    typeof cryptoImpl.randomUUID !== "function" ||
    !storage
  ) {
    throw new Error("Secure order submission is unavailable.");
  }

  const fingerprint = await hashPayload(
    fingerprintPayload,
    cryptoImpl
  );
  let storedSubmission;
  try {
    storedSubmission = JSON.parse(
      storage.getItem(PENDING_ORDER_SUBMISSION_KEY)
    );
  } catch {
    storedSubmission = null;
  }

  const idempotencyKey =
    storedSubmission?.fingerprint === fingerprint &&
    typeof storedSubmission.idempotencyKey === "string"
      ? storedSubmission.idempotencyKey
      : cryptoImpl.randomUUID();
  const requestedPickupAt =
    storedSubmission?.fingerprint === fingerprint &&
    typeof storedSubmission.requestedPickupAt === "string"
      ? storedSubmission.requestedPickupAt
      : payload.requested_pickup_at;

  storage.setItem(
    PENDING_ORDER_SUBMISSION_KEY,
    JSON.stringify({
      fingerprint,
      idempotencyKey,
      requestedPickupAt,
    })
  );

  const submission = JSON.parse(JSON.stringify(payload));
  submission.idempotency_key = idempotencyKey;
  submission.requested_pickup_at = requestedPickupAt;
  return freezeRecursively(submission);
}

export function clearOrderSubmission(
  storage = globalThis.sessionStorage,
) {
  storage?.removeItem(PENDING_ORDER_SUBMISSION_KEY);
}

export function getOrderErrorMessage(error) {
  if (error instanceof CloverCheckoutError) {
    return error.message;
  }
  if (!(error instanceof OrderApiError)) {
    return "We couldn’t finish your order. Please try again.";
  }

  switch (error.code) {
    case "request_validation_error":
      return "Please check your name, email, phone number, and order details.";
    case "pickup_invalid":
      return error.message;
    case "product_not_sellable":
      return "An item is no longer available. Please review your order.";
    case "variant_required":
    case "variant_invalid":
    case "modifier_option_invalid":
    case "modifier_selection_invalid":
      return "An item customization has changed. Please update your order.";
    case "idempotency_conflict":
      return "This order was already submitted with different details. Please refresh and try again.";
    default:
      return error.message || "We couldn’t finish your order. Please try again.";
  }
}
