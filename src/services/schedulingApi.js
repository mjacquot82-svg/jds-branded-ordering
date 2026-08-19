const SCHEDULING_OPTIONS_PATH = "/api/v1/scheduling/options";

export class SchedulingApiError extends Error {
  constructor(message, { code, status } = {}) {
    super(message);
    this.name = "SchedulingApiError";
    this.code = code;
    this.status = status;
  }
}

export function buildSchedulingLines(lines = []) {
  return lines
    .filter((line) => line.resolution === "ready")
    .map((line) => ({
      product_id: line.productBackendId,
      variant_id: line.options.find((option) => option.variantId)?.variantId ?? null,
      quantity: line.quantity,
    }));
}

export function resolveSchedulingSelection(schedule, intent = { type: "asap" }) {
  if (!schedule?.ordering_available) return null;
  if (intent.type === "custom") {
    return schedule.custom_pickup_at
      ? { key: "custom", requested_pickup_at: schedule.custom_pickup_at }
      : null;
  }
  if (intent.type === "preference") {
    const preferred = schedule.quick_pickup_options.find(
      (option) => option.preference_minutes === intent.minutes
    );
    if (preferred) return preferred;
  }
  return schedule.quick_pickup_options.find((option) => option.key === "asap") ?? null;
}

function requireSchedule(payload, status) {
  if (
    !payload ||
    typeof payload !== "object" ||
    typeof payload.ordering_available !== "boolean" ||
    !Array.isArray(payload.quick_pickup_options) ||
    !Number.isInteger(payload.minimum_lead_time_minutes) ||
    !Number.isInteger(payload.pickup_interval_minutes) ||
    !Number.isInteger(payload.maximum_advance_days)
  ) {
    throw new SchedulingApiError("Pickup scheduling returned an invalid response.", { status });
  }
  return payload;
}

export async function fetchSchedulingOptions(
  { lines, customPickupTime = null },
  {
    apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "",
    fetchImpl = globalThis.fetch,
    signal,
  } = {}
) {
  let response;
  try {
    response = await fetchImpl(
      `${apiBaseUrl.replace(/\/+$/, "")}${SCHEDULING_OPTIONS_PATH}`,
      {
        body: JSON.stringify({
          lines,
          custom_pickup_time: customPickupTime || null,
        }),
        credentials: "include",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        method: "POST",
        signal,
      }
    );
  } catch (cause) {
    if (cause?.name === "AbortError") throw cause;
    throw new SchedulingApiError("Unable to load pickup times.");
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new SchedulingApiError("Pickup scheduling returned an invalid response.", {
      status: response.status,
    });
  }
  if (!response.ok) {
    throw new SchedulingApiError(
      payload?.detail?.message || "Pickup scheduling is currently unavailable.",
      { code: payload?.detail?.code, status: response.status }
    );
  }
  return requireSchedule(payload, response.status);
}
