export function pickupTiming(order, now = new Date()) {
  const minutes = Math.round((new Date(order.requested_pickup_at) - now) / 60000);
  if (minutes < 0) return `${Math.abs(minutes)} min overdue`;
  if (minutes === 0) return "Due now";
  return `In ${minutes} min`;
}

export function ownerOrderAttentionReasons(order, now = new Date()) {
  const reasons = [];
  if (order.payment_status === "payment_failed") reasons.push("Payment failed");
  if (order.payment_status === "paid") {
    const pickupTime = new Date(order.requested_pickup_at).getTime();
    const minutesUntilPickup = (pickupTime - now.getTime()) / 60000;
    if (minutesUntilPickup < 0) reasons.push("Pickup overdue");
    else if (minutesUntilPickup <= 15) reasons.push("Pickup due within 15 minutes");
  }
  return reasons;
}

export function summarizeOwnerOrders(orders) {
  return orders.reduce((summary, order) => {
    if (order.payment_status === "payment_failed") summary.failed += 1;
    if (
      order.payment_status === "paid"
      && !["completed", "cancelled"].includes(order.fulfillment_status)
    ) summary.activePaid += 1;
    return summary;
  }, { activePaid: 0, failed: 0 });
}
