// Plain-words pickup time: "today at 3:15 PM", "tomorrow at 7:00 AM", "Sat, Nov 1 at 9:00 AM".
function dayKey(date, timeZone) {
  return new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone }).format(date);
}

export function describePickupTime(value, timeZone, now = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const time = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone }).format(date);
  const target = dayKey(date, timeZone);
  if (target === dayKey(now, timeZone)) return `today at ${time}`;
  if (target === dayKey(new Date(now.getTime() + 24 * 3600 * 1000), timeZone)) return `tomorrow at ${time}`;
  const day = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", timeZone }).format(date);
  return `${day} at ${time}`;
}

// ASAP normally means "in a few minutes". When the shop is closed it resolves to the
// next opening, which customers must see clearly before they pay.
export function asapIsLater(value, now = new Date(), thresholdMinutes = 60) {
  const date = value instanceof Date ? value : new Date(value);
  return !Number.isNaN(date.getTime()) && date.getTime() - now.getTime() > thresholdMinutes * 60 * 1000;
}

export function pickupSummaryText(value, timeZone, now = new Date()) {
  const described = describePickupTime(value, timeZone, now);
  return described ? `Ready ${described}` : "";
}
