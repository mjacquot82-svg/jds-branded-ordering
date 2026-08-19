import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, ShoppingBag } from "lucide-react";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { hasPermission, isOperationsAdministrator } from "../auth/ownerProductPermissions.js";
import {
  fetchActiveOwnerOrders,
  fetchOwnerOrderHistory,
  updateOwnerOrderFulfillment,
} from "../services/ownerOrdersApi.js";
import {
  ownerOrderAttentionReasons,
  pickupTiming,
  summarizeOwnerOrders,
} from "../services/ownerOrderPresentation.js";

const money = (cents, currency = "CAD") => new Intl.NumberFormat("en-CA", {
  currency,
  style: "currency",
}).format(cents / 100);

const STATUS_LABELS = {
  completed: "Completed",
  cancelled: "Cancelled",
};

const PAYMENT_LABELS = {
  pending: "Checkout not started",
  payment_pending: "Waiting for payment",
  paid: "Paid",
  payment_failed: "Payment failed",
};

const NEXT_ACTION = {
  new: ["Mark Completed", "completed"],
  preparing: ["Mark Completed", "completed"],
  ready: ["Mark Completed", "completed"],
};

function pickupTime(order) {
  return new Intl.DateTimeFormat("en-CA", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: order.business_timezone,
  }).format(new Date(order.requested_pickup_at));
}

function operationalTime(value, timezone) {
  if (!value) return null;
  return new Intl.DateTimeFormat("en-CA", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: timezone,
  }).format(new Date(value));
}

function itemSummary(order) {
  return order.items.slice(0, 2).map((item) => `${item.quantity} × ${item.product_name}`).join(", ")
    + (order.items.length > 2 ? ` + ${order.items.length - 2} more` : "");
}

function OrderDetail({ order, showFinancials }) {
  return (
    <div className="owner-order-detail">
      <div className="owner-order-customer">
        <div><span>Customer</span><strong>{order.customer_name}</strong></div>
        <a href={`tel:${order.customer_phone}`}>{order.customer_phone}</a>
        <a href={`mailto:${order.customer_email}`}>{order.customer_email}</a>
      </div>
      {order.notes ? <div className="owner-order-note"><strong>Order note</strong><p>{order.notes}</p></div> : null}
      <div className="owner-order-lines">
        {order.items.map((item, index) => (
          <div className="owner-order-line" key={`${item.product_slug}-${index}`}>
            <strong>{item.quantity} × {item.product_name}</strong>
            <span>{item.variant_name || "Standard"}</span>
            {item.modifiers.map((modifier) => (
              <small key={`${modifier.group_key}-${modifier.option_key}`}>{modifier.group_name}: {modifier.option_name}{(modifier.quantity || 1) > 1 ? ` x${modifier.quantity}` : ""}</small>
            ))}
            {showFinancials ? <b>{money(item.line_subtotal_cents, order.currency)}</b> : null}
          </div>
        ))}
      </div>
      {showFinancials ? <dl className="owner-order-totals">
        <div><dt>Subtotal</dt><dd>{money(order.subtotal_cents, order.currency)}</dd></div>
        <div><dt>{order.tax_name}</dt><dd>{money(order.tax_cents, order.currency)}</dd></div>
        <div><dt>Total</dt><dd>{money(order.total_cents, order.currency)}</dd></div>
      </dl> : null}
      <div className="owner-order-timeline" aria-label="Order progress">
        <span>Received {operationalTime(order.created_at, order.business_timezone)}</span>
        {order.fulfillment_timestamps.preparing_at ? <span>Preparing {operationalTime(order.fulfillment_timestamps.preparing_at, order.business_timezone)}</span> : null}
        {order.fulfillment_timestamps.ready_at ? <span>Ready {operationalTime(order.fulfillment_timestamps.ready_at, order.business_timezone)}</span> : null}
        {order.fulfillment_timestamps.completed_at ? <span>Completed {operationalTime(order.fulfillment_timestamps.completed_at, order.business_timezone)}</span> : null}
        {order.fulfillment_timestamps.cancelled_at ? <span>Cancelled {operationalTime(order.fulfillment_timestamps.cancelled_at, order.business_timezone)}</span> : null}
      </div>
      <p className="owner-order-created">Received {new Date(order.created_at).toLocaleString("en-CA")}</p>
    </div>
  );
}

function OrderCard({ administrator, busy, canFulfill, history, now, onAction, onCancel, onReturn, order }) {
  const [expanded, setExpanded] = useState(false);
  const next = NEXT_ACTION[order.fulfillment_status];
  const actionable = canFulfill && order.payment_status === "paid" && next;
  const returnable = history && canFulfill && order.payment_status === "paid" && order.fulfillment_status === "completed";
  const attentionReasons = history ? [] : ownerOrderAttentionReasons(order, now);
  const overdue = new Date(order.requested_pickup_at) < now;
  return (
    <article className={`owner-order-card status-${order.fulfillment_status} ${overdue ? "is-overdue" : ""}`}>
      <div className="owner-order-card-top">
        <div>
          <p className="owner-order-reference">{order.reference}</p>
          <h2>{order.customer_name}</h2>
          <p>{itemSummary(order)}</p>
        </div>
        <div className="owner-pickup-time">
          <span>Pickup</span><strong>{pickupTime(order)}</strong>
          <b className={overdue ? "overdue" : ""}>{pickupTiming(order, now)}</b>
        </div>
      </div>
      <div className="owner-order-badges">
        {STATUS_LABELS[order.fulfillment_status] ? <span className={`order-badge fulfillment-${order.fulfillment_status}`}>{STATUS_LABELS[order.fulfillment_status]}</span> : null}
        <span className={`order-badge payment-${order.payment_status}`}>{PAYMENT_LABELS[order.payment_status]}</span>
        <span>{order.item_count} item{order.item_count === 1 ? "" : "s"}</span>
        {administrator ? <strong>{money(order.total_cents, order.currency)}</strong> : null}
      </div>
      {order.payment_status !== "paid" ? (
        <p className="owner-order-warning"><AlertTriangle size={17} /> Payment is not complete. This order cannot be completed.</p>
      ) : null}
      {attentionReasons.length ? (
        <div className="owner-order-attention">
          <AlertTriangle size={17} />
          <div><strong>Needs attention</strong>{attentionReasons.map((reason) => <span key={reason}>{reason}</span>)}</div>
        </div>
      ) : null}
      {expanded ? <OrderDetail order={order} showFinancials={administrator} /> : null}
      <div className="owner-order-actions">
        <button className="secondary-button" type="button" onClick={() => setExpanded(!expanded)}>
          {expanded ? "Hide Details" : "View Details"}
        </button>
        {actionable ? (
          <button className="primary-button" disabled={busy} type="button" onClick={() => onAction(order, next[1])}>
            {busy ? "Updating…" : next[0]}
          </button>
        ) : null}
        {returnable ? (
          <button className="primary-button" disabled={busy} type="button" onClick={() => onReturn(order)}>
            {busy ? "Updating…" : "Return to Active"}
          </button>
        ) : null}
        {administrator && order.payment_status === "paid" && !["completed", "cancelled"].includes(order.fulfillment_status) ? (
          <button className="owner-cancel-button" disabled={busy} type="button" onClick={() => onCancel(order)}>Cancel Order</button>
        ) : null}
      </div>
    </article>
  );
}

function CancelDialog({ busy, onCancel, onClose, order }) {
  const dialog = useRef(null);
  useEffect(() => {
    dialog.current?.showModal();
    return () => dialog.current?.close();
  }, []);
  return (
    <dialog aria-labelledby="cancel-order-title" className="owner-confirm-dialog" onCancel={onClose} ref={dialog}>
      <h2 id="cancel-order-title">Cancel {order.reference}?</h2>
      <p>This removes the order from the active café queue. It does not issue a Clover refund.</p>
      <div className="form-actions">
        <button className="owner-danger-button" disabled={busy} type="button" onClick={onCancel}>{busy ? "Cancelling…" : "Cancel Order"}</button>
        <button className="secondary-button" disabled={busy} type="button" onClick={onClose}>Keep Order</button>
      </div>
    </dialog>
  );
}

export default function OrdersPage() {
  const { session } = useOwnerAuth();
  const administrator = isOperationsAdministrator(session);
  const canFulfill = administrator || hasPermission(session, "orders.fulfill");
  const [active, setActive] = useState([]);
  const [history, setHistory] = useState([]);
  const [view, setView] = useState("active");
  const [activeFilter, setActiveFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [cancelOrder, setCancelOrder] = useState(null);
  const knownIds = useRef(new Set());
  const busyRef = useRef(false);

  const refresh = useCallback(async ({ initial = false } = {}) => {
    if (!initial) setRefreshing(true);
    try {
      const orders = await fetchActiveOwnerOrders();
      const newOrders = orders.filter((order) => !knownIds.current.has(order.id) && order.payment_status === "paid");
      if (knownIds.current.size && newOrders.length) setNotice(`${newOrders.length} new paid order${newOrders.length === 1 ? "" : "s"} received.`);
      knownIds.current = new Set(orders.map((order) => order.id));
      setActive(orders);
      setError("");
      setLastUpdated(new Date());
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    refresh({ initial: true });
    const timer = window.setInterval(() => { if (!busyRef.current) refresh(); }, 20000);
    const onFocus = () => { if (!busyRef.current) refresh(); };
    window.addEventListener("focus", onFocus);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", onFocus); };
  }, [refresh]);

  async function showHistory() {
    setView("history"); setActiveFilter("all"); setError(""); setHistoryLoading(true);
    try { setHistory(await fetchOwnerOrderHistory()); }
    catch (loadError) { setError(loadError.message); }
    finally { setHistoryLoading(false); }
  }

  async function transition(order, status) {
    busyRef.current = true;
    setBusyId(order.id); setError("");
    try {
      await updateOwnerOrderFulfillment(order.id, status, order.version, session.csrf_token);
      setNotice(status === "cancelled" ? `${order.reference} cancelled.` : status === "new" ? `${order.reference} returned to Active Orders.` : `${order.reference} updated.`);
      setCancelOrder(null);
      await refresh();
      if (status === "new") {
        setHistory(await fetchOwnerOrderHistory());
        showActive();
      }
    } catch (actionError) {
      setError(actionError.message);
      await refresh();
    } finally { busyRef.current = false; setBusyId(null); }
  }

  function returnToActive(order) {
    if (window.confirm(`Return ${order.reference} to Active Orders?`)) transition(order, "new");
  }

  const operationalActive = active.filter(
    (order) => !["pending", "payment_pending"].includes(order.payment_status),
  );
  const counts = summarizeOwnerOrders(operationalActive);
  const now = new Date();
  const attentionOrders = operationalActive.filter(
    (order) => ownerOrderAttentionReasons(order, now).length > 0,
  );
  const filteredActive = operationalActive.filter((order) => {
    if (activeFilter === "paid") return order.payment_status === "paid";
    if (activeFilter === "attention") return attentionOrders.some(({ id }) => id === order.id);
    return true;
  });
  const orders = view === "active" ? filteredActive : history;
  const displayLoading = loading || (view === "history" && historyLoading);

  function showActive(filter = "all") {
    setView("active");
    setActiveFilter(filter);
  }

  return (
    <section className="page-section owner-orders-page">
      <div className="owner-orders-heading">
        <div><p className="eyebrow">Today’s café queue</p><h1>Orders</h1><p>Paid orders stay active until completed. Payment problems stay clearly flagged.</p></div>
        <button className="secondary-button" disabled={refreshing || busyId !== null} type="button" onClick={() => refresh()}><RefreshCw size={17} /> {refreshing ? "Refreshing…" : "Refresh"}</button>
      </div>
      <div className="owner-order-summary" aria-label="Order summary">
        <button aria-pressed={view === "active" && activeFilter === "paid"} type="button" onClick={() => showActive("paid")}><span>Active paid</span><strong>{loading ? "—" : counts.activePaid}</strong></button>
        <button aria-pressed={view === "active" && activeFilter === "attention"} type="button" onClick={() => showActive("attention")}><span>Needs attention</span><strong>{loading ? "—" : attentionOrders.length}</strong></button>
      </div>
      <div className="owner-orders-toolbar">
        <div role="tablist" aria-label="Order views">
          <button aria-selected={view === "active"} role="tab" type="button" onClick={() => showActive()}>Active orders</button>
          <button aria-selected={view === "history"} role="tab" type="button" onClick={showHistory}>Recent history</button>
        </div>
        {view === "active" && activeFilter !== "all" ? <button className="owner-orders-clear-filter" type="button" onClick={() => showActive()}>Show all active orders</button> : null}
        <span>{lastUpdated ? `Last updated ${lastUpdated.toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit", second: "2-digit" })}` : "Not updated yet"}</span>
      </div>
      {notice ? <p className="owner-orders-notice" role="status"><CheckCircle2 size={18} /> {notice}</p> : null}
      {error ? <div className="owner-orders-error" role="alert"><AlertTriangle size={18} /><div><strong>Orders may be out of date.</strong><p>{error}</p></div><button type="button" onClick={() => view === "history" ? showHistory() : refresh()}>Try again</button></div> : null}
      {displayLoading ? <div className="owner-order-skeletons" aria-label="Loading orders"><div /><div /><div /></div> : null}
      {!displayLoading && !orders.length ? <div className="owner-orders-empty"><ShoppingBag size={28} /><h2>{view === "active" && activeFilter !== "all" ? "No orders match this summary" : view === "active" ? "No active orders" : "No recent order history"}</h2><p>{view === "active" && activeFilter !== "all" ? "Show all active orders to return to the full queue." : view === "active" ? "Paid orders will appear here automatically." : "Completed and cancelled orders will appear here."}</p></div> : null}
      {!displayLoading && orders.length ? <div className="owner-order-list">{orders.map((order) => <OrderCard administrator={administrator} busy={busyId === order.id} canFulfill={canFulfill} history={view === "history"} key={order.id} now={now} onAction={transition} onCancel={setCancelOrder} onReturn={returnToActive} order={order} />)}</div> : null}
      {administrator && cancelOrder ? <CancelDialog busy={busyId === cancelOrder.id} onCancel={() => transition(cancelOrder, "cancelled")} onClose={() => setCancelOrder(null)} order={cancelOrder} /> : null}
    </section>
  );
}
