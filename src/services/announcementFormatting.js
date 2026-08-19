const cad = (cents) => new Intl.NumberFormat("en-CA", { currency: "CAD", style: "currency" }).format(cents / 100);

export function lunchSpecialAnnouncement(special) {
  if (!special) return "";
  return `Today’s Lunch Special is ${special.name} for ${cad(special.price_cents)}. Order online while it’s available!`;
}
