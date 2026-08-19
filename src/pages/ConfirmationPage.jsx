import { useEffect, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { clearOrderSubmission } from "../services/checkoutOrder.js";
import { fetchPendingOrder } from "../services/orderApi.js";
import { removeTenantLocalStorage } from "../services/tenantBrowserState.js";

function formatPrice(cents) {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
  }).format(cents / 100);
}

function formatPickupTime(value) {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function ConfirmationPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const publicToken = searchParams.get("order") || "";
  const paymentResult = searchParams.get("payment");
  const suppliedOrder =
    location.state?.order?.public_token === publicToken
      ? location.state.order
      : null;
  const [state, setState] = useState({
    status: suppliedOrder ? "ready" : "loading",
    order: suppliedOrder,
  });
  const [reloadSequence, setReloadSequence] = useState(0);

  useEffect(() => {
    if (suppliedOrder) {
      return undefined;
    }
    if (!publicToken) {
      setState({ status: "missing", order: null });
      return undefined;
    }

    const controller = new AbortController();
    setState({ status: "loading", order: null });
    fetchPendingOrder(publicToken, { signal: controller.signal })
      .then((order) => setState({ status: "ready", order }))
      .catch((error) => {
        if (error.cause?.name !== "AbortError") {
          setState({ status: "error", order: null });
        }
      });
    return () => controller.abort();
  }, [publicToken, reloadSequence, suppliedOrder]);

  const order = state.order;

  useEffect(() => {
    if (
      paymentResult !== "success" ||
      order?.status !== "payment_pending" ||
      reloadSequence >= 10
    ) {
      return undefined;
    }
    const timer = window.setTimeout(
      () => setReloadSequence((value) => value + 1),
      1500
    );
    return () => window.clearTimeout(timer);
  }, [order?.status, paymentResult, reloadSequence]);

  useEffect(() => {
    if (order?.status !== "paid") {
      return;
    }
    clearOrderSubmission();
    removeTenantLocalStorage("cafe-cart");
  }, [order?.status]);

  return (
    <section className="page-section compact-section ordering-page">
      <div className="confirmation-panel">
        <span className="confirmation-icon" aria-hidden="true">
          <CheckCircle2 size={24} strokeWidth={2.4} />
        </span>
        <h1>
          {order?.status === "paid"
            ? "Payment received"
            : order?.status === "payment_failed" || paymentResult === "failure"
              ? "Payment failed"
              : paymentResult === "cancelled"
                ? "Checkout cancelled"
                : "Confirming payment"}
        </h1>
        {order ? (
          <>
            <p>
              {order.status === "paid"
                ? `Thanks, ${order.customer.name}. We have your paid order for pickup ${formatPickupTime(order.requested_pickup_at)}.`
                : order.status === "payment_failed" || paymentResult === "failure"
                  ? "Clover could not complete the payment. Your cart was saved as a pending order; please try checkout again."
                  : paymentResult === "cancelled"
                    ? "No payment was completed. You can return to the menu and try again."
                    : "Clover returned you to the shop. We are waiting for its signed payment confirmation."}
            </p>
            <div className="confirmation-summary">
              <span>Order {order.public_token.slice(0, 8).toUpperCase()}</span>
              <strong>{formatPrice(order.total_cents)}</strong>
            </div>
            <ul className="order-item-list">
              {order.items.map((item, index) => (
                <li key={`${item.product_slug}-${index}`}>
                  <span>
                    {item.quantity} ×{" "}
                    {item.variant_name ? `${item.variant_name} ` : ""}
                    {item.product_name}
                  </span>
                  <strong>{formatPrice(item.line_subtotal_cents)}</strong>
                </li>
              ))}
            </ul>
          </>
        ) : state.status === "loading" ? (
          <p role="status">Loading your order details.</p>
        ) : state.status === "error" ? (
          <>
            <p role="alert">
              We couldn’t load your order details. Please check your connection
              and try again.
            </p>
            <button
              className="primary-button"
              type="button"
              onClick={() => setReloadSequence((value) => value + 1)}
            >
              Try again
            </button>
          </>
        ) : (
          <p role="alert">
            This confirmation link is incomplete. Return home to start a new
            order.
          </p>
        )}
        <div className="confirmation-actions">
          <Link className="secondary-button" to="/">
            Return Home
          </Link>
        </div>
      </div>
    </section>
  );
}
