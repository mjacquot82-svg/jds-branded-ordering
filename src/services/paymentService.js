// Future Stripe/Clover payment confirmation placeholder.

export async function confirmPayment(order) {
  console.log("Future payment confirmation:", order);
  return {
    paid: true,
    paymentId: `pay_mock_${Date.now()}`
  };
}
