// Future notification placeholder.
// Could become Clover device notification, SMS, email, or push.

export async function notifyStaff(order) {
  console.log("Future staff notification:", order);
  return { sent: true };
}
