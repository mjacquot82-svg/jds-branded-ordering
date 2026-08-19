import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ReceiptText } from "lucide-react";
import { useCustomerAuth } from "../auth/CustomerAuthContext.jsx";
import { fetchCustomerOrder, fetchCustomerOrders } from "../services/customerAccountApi.js";
import { useCustomerCatalog } from "../stores/customerCatalogStore.js";
import { getCustomerErrorMessage } from "../services/customerMessages.js";
import { formatConfigurationDescription, groupConfigurationSelections } from "../services/configurationDescription.js";

const money = (cents) => new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(cents / 100);
const friendlyStatus = (value) => ({ paid: "Paid", completed: "Completed", ready: "Ready", preparing: "Preparing", new: "Received", cancelled: "Cancelled" })[value] || "In progress";
const orderDate = (value, timeZone) => new Intl.DateTimeFormat("en-CA", { dateStyle: "medium", timeZone }).format(new Date(value));
const pickupTime = (value, timeZone) => new Intl.DateTimeFormat("en-CA", { hour: "numeric", minute: "2-digit", timeZone }).format(new Date(value));

function summaryConfiguration(order) {
  if (order.item_count !== 1) return "";
  const item = order.first_item;
  return formatConfigurationDescription([
    ...(item.variant_name ? [{ groupName: "Size", name: item.variant_name }] : []),
    ...item.modifiers.map((modifier) => ({
      groupName: modifier.group_name,
      name: modifier.option_name,
      quantity: modifier.quantity,
    })),
  ]);
}

function summaryTitle(order) {
  const item = order.first_item;
  if (order.item_count === 1) return item.product_name;
  const firstQuantity = Math.min(item.quantity, order.item_count);
  const remaining = order.item_count - firstQuantity;
  return `${firstQuantity > 1 ? `${firstQuantity} × ` : ""}${item.product_name}${remaining ? ` + ${remaining} more item${remaining === 1 ? "" : "s"}` : ""}`;
}

function reorderCart(order, catalog) {
  const cart = [];
  for (const item of order.items) {
    const product = catalog?.products.find((candidate) => candidate.slug === item.product_slug);
    if (!product?.available) return null;
    const selected = [];
    if (item.variant_key) {
      const group = product.modifierGroups.find((candidate) => candidate.id === "size");
      const option = group?.options.find((candidate) => candidate.id === item.variant_key);
      if (group && option) selected.push({ group, option, quantity: 1 });
      else return null;
    }
    for (const modifier of item.modifiers) {
      const group = product.modifierGroups.find((candidate) => candidate.id === modifier.group_key);
      const option = group?.options.find((candidate) => candidate.id === modifier.option_key);
      if (group && option) selected.push({ group, option, quantity: modifier.quantity || 1 });
      else return null;
    }
    for (const group of product.modifierGroups.filter((candidate) => candidate.id !== "size")) {
      const groupSelections = selected.filter((value) => value.group.id === group.id);
      const total = groupSelections.reduce((sum, value) => sum + value.quantity, 0);
      if ((group.type === "single" && groupSelections.length > 1) || (!group.allowQuantity && groupSelections.some((value) => value.quantity !== 1)) || total < group.minSelections || (group.maxSelections > 0 && total > group.maxSelections)) return null;
    }
    const signature = selected.map(({ group, option, quantity }) => `${group.id}:${option.id}${quantity > 1 ? `:${quantity}` : ""}`).sort().join("|");
    cart.push({
      id: signature ? `${product.id}__${signature}` : product.id,
      productId: product.id, name: product.name, description: product.description,
      price: product.price + selected.reduce((sum, value) => sum + value.option.priceDelta * value.quantity, 0),
      basePrice: product.price, category: product.category, quantity: item.quantity,
      options: selected.map(({ group, option, quantity }) => ({ groupName: group.name, groupId: group.id, name: option.name, backendId: option.backendId, variantId: option.variantId, priceDelta: option.priceDelta, quantity })),
    });
  }
  return cart;
}

export default function OrdersPageMobile() {
  const navigate = useNavigate();
  const { session, status: authStatus } = useCustomerAuth();
  const { catalog } = useCustomerCatalog();
  const [orders, setOrders] = useState([]);
  const [detail, setDetail] = useState(null);
  const [message, setMessage] = useState("");
  useEffect(() => { if (session) fetchCustomerOrders().then(setOrders).catch((error) => setMessage(getCustomerErrorMessage(error, "We couldn’t load your orders. Please try again."))); }, [session]);
  if (authStatus === "loading") return <section className="page-section compact-section"><p>Checking your orders…</p></section>;
  if (!session) return <section className="page-section ordering-page app-simple-page"><div className="ordering-top-card compact-app-heading"><div><p className="eyebrow">Order history</p><h1>Orders</h1><p>Sign in to view orders placed with your customer account.</p></div></div><div className="form-actions"><Link className="primary-button" to="/login">Sign In</Link><Link className="secondary-button" to="/register">Create Account</Link></div></section>;
  async function showOrder(id) { try { setDetail(await fetchCustomerOrder(id)); } catch (error) { setMessage(getCustomerErrorMessage(error, "We couldn’t load that order. Please try again.")); } }
  function reorder() {
    const cart = reorderCart(detail, catalog);
    if (!cart?.length) { setMessage("This order’s exact configuration is no longer available. Please customize it from the current menu."); return; }
    window.localStorage.setItem("cafe-cart", JSON.stringify(cart));
    navigate("/cart");
  }
  return <section className="page-section ordering-page app-simple-page">
    <div className="ordering-top-card compact-app-heading"><div><p className="eyebrow">Order history</p><h1>Orders</h1><p>Your previous customer-account orders.</p></div></div>
    {message ? <p className="form-status">{message}</p> : null}
    {detail ? <article className="content-block app-content-block order-detail-card">
      <header className="order-detail-heading"><div><p className="eyebrow">Order</p><h2>{detail.public_token.slice(0, 8).toUpperCase()}</h2></div><div className="order-statuses"><span>{friendlyStatus(detail.fulfillment_status)}</span><span>{friendlyStatus(detail.status)}</span></div></header>
      <div className="order-detail-timing"><time>{orderDate(detail.created_at, detail.business_timezone)}</time><span>Pickup {pickupTime(detail.requested_pickup_at, detail.business_timezone)}</span></div>
      <div className="order-history-items">{detail.items.map((item, index) => {
        const groups = groupConfigurationSelections([
          ...(item.variant_name ? [{ groupName: "Size", name: item.variant_name }] : []),
          ...item.modifiers.map((modifier) => ({ groupName: modifier.group_name, name: modifier.option_name, quantity: modifier.quantity })),
        ]);
        return <section key={`${item.product_slug}-${item.variant_key || "standard"}-${index}`}><div><h3>{item.quantity} × {item.product_name}</h3><strong>{money(item.line_subtotal_cents)}</strong></div>{groups.length ? <dl>{groups.map((group) => <div key={group.name}><dt>{group.name}</dt><dd>{group.options.join(", ")}</dd></div>)}</dl> : null}</section>;
      })}</div>
      <dl className="order-history-totals"><div><dt>Subtotal</dt><dd>{money(detail.subtotal_cents)}</dd></div><div><dt>{detail.tax_name || "Tax"}</dt><dd>{money(detail.tax_cents)}</dd></div><div className="order-history-total"><dt>Total</dt><dd>{money(detail.total_cents)}</dd></div></dl>
      <div className="form-actions"><button className="primary-button" type="button" onClick={reorder}>Reorder</button><button className="secondary-button" type="button" onClick={() => setDetail(null)}>Collapse</button></div>
    </article> : null}
    {!detail && orders.length ? <div className="account-settings-list order-history-list">{orders.map((order) => <button className="content-block app-content-block compact-info-row order-history-row" key={order.id} type="button" onClick={() => showOrder(order.id)}><ReceiptText aria-hidden="true" size={18} /><span className="order-history-summary"><strong>{summaryTitle(order)}</strong>{summaryConfiguration(order) ? <small>{summaryConfiguration(order)}</small> : null}<span><time>{orderDate(order.created_at, order.business_timezone)}</time><em>{friendlyStatus(order.fulfillment_status)}</em></span></span><strong>{money(order.total_cents)}</strong></button>)}</div> : null}
    {!detail && !orders.length ? <div className="content-block app-content-block app-status-card"><ReceiptText size={20} /><div><h2>No previous orders</h2><p>Your first signed-in order will appear here.</p></div><Link className="primary-button" to="/menu">Browse menu</Link></div> : null}
  </section>;
}
