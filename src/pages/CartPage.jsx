import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ClipboardList, CreditCard, Minus, Plus, Trash2, UserRound } from "lucide-react";
import { resolveCart } from "../services/cartCatalog.js";
import {
  buildPendingOrderRequest,
  clearOrderSubmission,
  createSubmissionGate,
  getOrderErrorMessage,
  formatPickupTimeInput,
  prepareOrderSubmission,
  resolveVisibleCheckoutContact,
  isCheckoutContactComplete,
} from "../services/checkoutOrder.js";
import { createPendingOrder } from "../services/orderApi.js";
import { createCloverCheckout } from "../services/cloverService.js";
import { useCustomerCatalog } from "../stores/customerCatalogStore.js";
import { isOrderingCustomerSession, useCustomerAuth } from "../auth/CustomerAuthContext.jsx";
import { fetchCustomerProfile } from "../services/customerAccountApi.js";
import { formatCustomerPhone } from "../services/customerPhone.js";
import { formatTaxLabel, getOrderPricing } from "../services/orderPricing.js";
import { formatConfigurationDescription } from "../services/configurationDescription.js";
import {
  buildSchedulingLines,
  fetchSchedulingOptions,
  resolveSchedulingSelection,
} from "../services/schedulingApi.js";
import { readTenantLocalStorage, writeTenantLocalStorage } from "../services/tenantBrowserState.js";
import { useTenant } from "../tenant/TenantContext.jsx";

function formatPrice(price) {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
  }).format(price);
}

function getStoredCart() {
  try {
    return JSON.parse(readTenantLocalStorage("cafe-cart")) || [];
  } catch {
    return [];
  }
}

function storeCart(cart) {
  writeTenantLocalStorage("cafe-cart", JSON.stringify(cart));
}

function getStoredPickupIntent() {
  try {
    const stored = readTenantLocalStorage("pickup-intent");
    const intent = stored ? JSON.parse(stored) : null;
    if (intent?.type === "custom" || intent?.type === "asap") return intent;
    if (intent?.type === "preference" && Number.isInteger(intent.minutes)) return intent;
  } catch {
    // Fall through to the backend ASAP default.
  }
  return { type: "asap" };
}

function storePickupIntent(intent) {
  writeTenantLocalStorage("pickup-intent", JSON.stringify(intent));
}

function getStoredCustomPickupTime() {
  try {
    return readTenantLocalStorage("custom-pickup-time") || "";
  } catch {
    return "";
  }
}

function storeCustomPickupTime(value) {
  writeTenantLocalStorage("custom-pickup-time", value);
}

function formatReadyTime(date, timeZone) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  }).format(date);
}

export default function CartPage() {
  const tenant = useTenant();
  const stagingPaymentsDisabled = tenant.value?.review?.paymentMode === "fixture-disabled";
  const { session } = useCustomerAuth();
  const orderingCustomer = isOrderingCustomerSession(session);
  const { status, catalog, reload } = useCustomerCatalog();
  const [cart, setCart] = useState(getStoredCart);
  const [pickupIntent, setPickupIntent] = useState(getStoredPickupIntent);
  const [customPickupTime, setCustomPickupTime] = useState(getStoredCustomPickupTime);
  const [schedule, setSchedule] = useState(null);
  const [scheduleStatus, setScheduleStatus] = useState("loading");
  const [scheduleError, setScheduleError] = useState("");
  const [checkoutContact, setCheckoutContact] = useState({
    name: "",
    email: "",
    phone: "",
  });
  const checkoutContactRef = useRef(checkoutContact);
  const checkoutContactInputsRef = useRef({});
  const [orderNotes, setOrderNotes] = useState("");
  const [checkoutError, setCheckoutError] = useState("");
  const [isPlacingOrder, setIsPlacingOrder] = useState(false);
  const [savedOrder, setSavedOrder] = useState(null);
  const [showAuthRequirement, setShowAuthRequirement] = useState(false);
  const authRequirementRef = useRef(null);
  const submissionGate = useRef(createSubmissionGate());
  useEffect(() => {
    if (!orderingCustomer) return;
    let isCurrent = true;

    fetchCustomerProfile()
      .then((profile) => {
        if (!isCurrent) return;

        const contact = {
          name: profile.name || "",
          email: profile.email || "",
          phone: formatCustomerPhone(profile.phone || ""),
        };
        checkoutContactRef.current = contact;
        setCheckoutContact(contact);
        if (profile.preferred_pickup_minutes != null) {
          updatePickupIntent({ type: "preference", minutes: profile.preferred_pickup_minutes });
        }
        if (profile.preferred_pickup_notes) setOrderNotes(profile.preferred_pickup_notes);
      })
      .catch(() => {
        if (isCurrent) {
          setCheckoutError("We couldn’t load your saved contact details. Please enter them before placing your order.");
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [orderingCustomer]);
  const resolvedCart = useMemo(
    () => resolveCart(catalog, cart),
    [catalog, cart]
  );
  const schedulingLines = useMemo(
    () => buildSchedulingLines(resolvedCart.lines),
    [resolvedCart.lines]
  );
  const schedulingLinesKey = JSON.stringify(schedulingLines);
  const refreshScheduling = useCallback(async ({ signal } = {}) => {
    if (!schedulingLines.length) return null;
    setScheduleStatus("loading");
    try {
      const value = await fetchSchedulingOptions({
        lines: schedulingLines,
        customPickupTime: pickupIntent.type === "custom" ? customPickupTime : null,
      }, { signal });
      setSchedule(value);
      setScheduleStatus("ready");
      setScheduleError("");
      return value;
    } catch (error) {
      if (error?.name === "AbortError") return null;
      setSchedule(null);
      setScheduleStatus("error");
      setScheduleError(error.message || "Pickup scheduling is currently unavailable.");
      return null;
    }
  }, [customPickupTime, pickupIntent.type, schedulingLinesKey]);
  useEffect(() => {
    if (status !== "ready" || resolvedCart.hasStaleLines || !schedulingLines.length) return;
    const controller = new AbortController();
    refreshScheduling({ signal: controller.signal });
    return () => controller.abort();
  }, [refreshScheduling, resolvedCart.hasStaleLines, schedulingLines.length, status]);
  const orderPricing = useMemo(
    () => getOrderPricing(resolvedCart.totalCents, catalog.pricing),
    [catalog.pricing, resolvedCart.totalCents]
  );
  const selectedPickup = resolveSchedulingSelection(schedule, pickupIntent);
  const pickupSummary = selectedPickup?.requested_pickup_at
    ? `Ready around ${formatReadyTime(new Date(selectedPickup.requested_pickup_at), schedule.business_timezone)}`
    : scheduleStatus === "loading" ? "Checking pickup times…" : "Pickup time unavailable";
  const resolvedPickupTime = formatPickupTimeInput(
    selectedPickup?.requested_pickup_at,
    schedule?.business_timezone
  );
  const checkoutLocked = isPlacingOrder || Boolean(savedOrder);

  function updateQuantity(itemId, nextQuantity) {
    if (submissionGate.current.isInFlight() || savedOrder) {
      return;
    }
    const nextCart =
      nextQuantity <= 0
        ? cart.filter((item) => item.id !== itemId)
        : cart.map((item) => (item.id === itemId ? { ...item, quantity: nextQuantity } : item));

    setCart(nextCart);
    storeCart(nextCart);
    if (!nextCart.length) {
      clearOrderSubmission();
    }
  }

  function updatePickupIntent(intent) {
    if (submissionGate.current.isInFlight() || savedOrder) {
      return;
    }
    setPickupIntent(intent);
    storePickupIntent(intent);
  }

  function updateCustomPickupTime(value) {
    if (!value || submissionGate.current.isInFlight() || savedOrder) return;

    setCustomPickupTime(value);
    storeCustomPickupTime(value);
    updatePickupIntent({ type: "custom" });
  }

  function beginCustomPickup() {
    if (checkoutLocked || pickupIntent.type === "custom") return;
    if (resolvedPickupTime) {
      setCustomPickupTime(resolvedPickupTime);
      storeCustomPickupTime(resolvedPickupTime);
    }
    updatePickupIntent({ type: "custom" });
  }

  function updateCheckoutContact(field, value) {
    if (submissionGate.current.isInFlight() || savedOrder) {
      return;
    }
    const nextContact = { ...checkoutContactRef.current, [field]: value };
    checkoutContactRef.current = nextContact;
    setCheckoutContact(nextContact);
  }

  function updateOrderNotes(value) {
    if (submissionGate.current.isInFlight() || savedOrder) {
      return;
    }
    setOrderNotes(value);
  }

  async function placeOrder() {
    if (!orderingCustomer) {
      setShowAuthRequirement(true);
      window.requestAnimationFrame(() => authRequirementRef.current?.focus());
      return;
    }
    const visibleContact = Object.fromEntries(
      Object.entries(checkoutContactInputsRef.current).map(([field, input]) => [
        field,
        input?.value,
      ])
    );
    const canonicalContact = resolveVisibleCheckoutContact(
      checkoutContactRef.current,
      visibleContact
    );
    if (!submissionGate.current.begin()) {
      setCheckoutError("Your order is already being submitted. Please wait.");
      return;
    }
    if (!isCheckoutContactComplete(canonicalContact)) {
      setCheckoutError(
        "Add your first and last name, email, and phone number before placing your order."
      );
      submissionGate.current.end();
      return;
    }

    setIsPlacingOrder(true);
    setCheckoutError("");

    try {
      if (!schedule?.ordering_available || !selectedPickup?.requested_pickup_at) {
        throw new Error(schedule?.unavailable_reason || schedule?.custom_pickup_error || "Choose an available pickup time.");
      }
      const requestedPickupAt = selectedPickup.requested_pickup_at;
      const request = buildPendingOrderRequest({
        contact: canonicalContact,
        idempotencyKey: "",
        lines: resolvedCart.lines,
        notes: orderNotes,
        requestedPickupAt,
      });
      const submission = await prepareOrderSubmission(request);
      const order = await createPendingOrder(submission);
      setSavedOrder(order);
      const checkout = await createCloverCheckout(order.public_token);

      window.location.assign(checkout.checkout_url);
    } catch (error) {
      setCheckoutError(getOrderErrorMessage(error));
      if (error?.code === "pickup_invalid") {
        clearOrderSubmission();
        await refreshScheduling();
      }
    } finally {
      submissionGate.current.end();
      setIsPlacingOrder(false);
    }
  }

  async function retryPayment() {
    if (!savedOrder || !submissionGate.current.begin()) return;
    setIsPlacingOrder(true);
    setCheckoutError("");
    try {
      const checkout = await createCloverCheckout(savedOrder.public_token);
      window.location.assign(checkout.checkout_url);
    } catch (error) {
      setCheckoutError(getOrderErrorMessage(error));
    } finally {
      submissionGate.current.end();
      setIsPlacingOrder(false);
    }
  }

  if (!cart.length) {
    return (
      <section className="page-section compact-section ordering-page">
        <div className="empty-state">
          <h1>Your cart is empty</h1>
          <p>Add coffee, tea, pastries, or a little flavour shot when you are ready.</p>
          <Link className="primary-button" to="/menu">
            Browse menu
          </Link>
        </div>
      </section>
    );
  }

  if (status === "idle" || status === "loading") {
    return (
      <section className="page-section compact-section ordering-page">
        <div className="empty-state" role="status" aria-live="polite">
          <h1>Checking your café bag</h1>
          <p>Confirming today’s menu and your customizations.</p>
        </div>
      </section>
    );
  }

  if (status === "error") {
    return (
      <section className="page-section compact-section ordering-page">
        <div className="empty-state" role="alert">
          <h1>We couldn’t check your café bag</h1>
          <p>Please check your connection and try again.</p>
          <button className="primary-button" type="button" onClick={reload}>
            Try again
          </button>
        </div>
      </section>
    );
  }

  if (savedOrder) {
    return (
      <section className="page-section ordering-page cart-page saved-order-page">
        <div className="page-heading cart-heading">
          <span className="eyebrow">Order accepted</span>
          <h1>The café has your order</h1>
          <p>{stagingPaymentsDisabled ? "This synthetic order is for product review only. Real payment is disabled." : "Your pickup time is confirmed. Payment is the only step left."}</p>
        </div>

        <div className="saved-order-status" role="status" aria-live="polite">
          <div className="saved-order-status-heading">
            <span className="saved-order-check" aria-hidden="true">✓</span>
            <div>
              <strong>Your order is confirmed</strong>
              <span>Order {savedOrder.public_token.slice(0, 8).toUpperCase()}</span>
            </div>
          </div>
          <div className="saved-order-milestones" aria-label="Order status">
            <div className="saved-order-complete"><span>✓ Pickup confirmed</span><strong>{formatReadyTime(new Date(savedOrder.requested_pickup_at), savedOrder.business_timezone)}</strong></div>
            <div className="saved-order-payment-pending"><span>Payment needed</span><strong>Complete now</strong></div>
          </div>
          {checkoutError ? (
            <p className="saved-order-payment-note" role="alert">
              Secure payment could not be started. Please try again. If it continues to fail, contact the café and mention your order number.
            </p>
          ) : (
            <p>Complete secure payment below. Your order will not be submitted again.</p>
          )}
        </div>

        <div className="content-block saved-order-summary">
          <div className="saved-order-summary-heading">
            <div><span>Order summary</span><h2>Your café picks</h2></div>
            <strong>{formatPrice(savedOrder.total_cents / 100)}</strong>
          </div>
          <ul>
            {savedOrder.items.map((item, index) => (
              <li key={`${item.product_slug}-${item.variant_key || "standard"}-${index}`}>
                <div>
                  <strong>{item.quantity} × {item.product_name}</strong>
                  {item.variant_name ? <span>{item.variant_name}</span> : null}
                  {item.modifiers?.length ? <small>{formatConfigurationDescription(item.modifiers)}</small> : null}
                </div>
                <strong>{formatPrice(item.line_subtotal_cents / 100)}</strong>
              </li>
            ))}
          </ul>
          <dl className="saved-order-details">
            <div><dt>Contact</dt><dd>{savedOrder.customer.name}<br />{savedOrder.customer.email}<br />{formatCustomerPhone(savedOrder.customer.phone)}</dd></div>
            {savedOrder.notes ? <div><dt>Order notes</dt><dd>{savedOrder.notes}</dd></div> : null}
          </dl>
          <div className="cart-total-row cart-pricing-breakdown">
            <span>Subtotal</span><strong>{formatPrice(savedOrder.subtotal_cents / 100)}</strong>
            <span>{formatTaxLabel(catalog.pricing)}</span><strong>{formatPrice(savedOrder.tax_cents / 100)}</strong>
            <span>Total</span><strong>{formatPrice(savedOrder.total_cents / 100)}</strong>
          </div>
          <button
            aria-busy={isPlacingOrder}
            className="primary-button"
            disabled={isPlacingOrder || stagingPaymentsDisabled}
            type="button"
            onClick={retryPayment}
          >
            <CreditCard size={17} strokeWidth={2.4} />
            {stagingPaymentsDisabled ? "Real payments disabled in staging" : isPlacingOrder ? "Starting secure payment…" : "Complete secure payment"}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="page-section ordering-page cart-page">
      <div className="page-heading cart-heading">
        <h1>Your order</h1>
        <p>Review your café picks before placing your order.</p>
      </div>

      <div className="content-block cart-review app-cart-review">
        <ul>
          {resolvedCart.lines.map((item) => (
            <li key={item.id}>
              <div className="cart-item-copy">
                <strong>{item.name}</strong>
                {item.options?.length ? (
                  <small>
                    {formatConfigurationDescription(item.options)}
                  </small>
                ) : null}
                <span>
                  {item.quantity} x {formatPrice(item.price)}
                </span>
                {item.resolution !== "ready" ? (
                  <small role="alert">
                    {item.issues.join(" ")} Remove it or add a current version from the menu.
                  </small>
                ) : null}
              </div>
              <div className="cart-line-actions">
                <strong>
                  {item.resolution === "ready"
                    ? formatPrice(item.price * item.quantity)
                    : "Unavailable"}
                </strong>
                {item.resolution === "ready" ? (
                  <div className="quantity-stepper" aria-label={`Quantity for ${item.name}`}>
                    <button
                      disabled={checkoutLocked}
                      type="button"
                      aria-label={`Remove one ${item.name}`}
                      onClick={() => updateQuantity(item.id, item.quantity - 1)}
                    >
                      <Minus size={16} />
                    </button>
                    <span>{item.quantity}</span>
                    <button
                      disabled={checkoutLocked}
                      type="button"
                      aria-label={`Add one ${item.name}`}
                      onClick={() => updateQuantity(item.id, item.quantity + 1)}
                    >
                      <Plus size={16} />
                    </button>
                  </div>
                ) : null}
                <button
                  className="remove-cart-item"
                  disabled={checkoutLocked}
                  type="button"
                  aria-label={`Remove ${item.name}`}
                  onClick={() => updateQuantity(item.id, 0)}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </li>
          ))}
        </ul>
        <div className="pickup-timing-panel">
          <div className="pickup-timing-heading">
            <div>
              <span>Preferred pickup time</span>
              <h2>When should we have it ready?</h2>
            </div>
            <strong>{pickupSummary}</strong>
          </div>
          <div className="pickup-time-options" role="radiogroup" aria-label="Quick pickup timing">
            {(schedule?.quick_pickup_options || []).map((option) => {
              const optionIntent = option.preference_minutes == null
                ? { type: "asap" }
                : { type: "preference", minutes: option.preference_minutes };
              const isSelected = selectedPickup?.key === option.key && pickupIntent.type !== "custom";
              return (
              <label key={option.key} className={isSelected ? "selected" : ""}>
                <input
                  checked={isSelected}
                  disabled={checkoutLocked}
                  name="pickup-time"
                  type="radio"
                  value={option.key}
                  onChange={() => updatePickupIntent(optionIntent)}
                />
                <span>{option.label}</span>
              </label>
              );
            })}
          </div>
          <div className={`custom-pickup-time${pickupIntent.type === "custom" ? " selected" : ""}`}>
            <label htmlFor="custom-pickup-time">Ready around...</label>
            <input
              id="custom-pickup-time"
              disabled={checkoutLocked}
              required
              step={schedule ? schedule.pickup_interval_minutes * 60 : undefined}
              type="time"
              value={pickupIntent.type === "custom" ? customPickupTime : resolvedPickupTime}
              onChange={(event) => updateCustomPickupTime(event.target.value)}
              onFocus={beginCustomPickup}
            />
            {pickupIntent.type === "custom" && schedule?.custom_pickup_error ? (
              <small role="alert">{schedule.custom_pickup_error}</small>
            ) : null}
          </div>
        </div>
        <div className="checkout-contact-panel">
          <div className="checkout-contact-heading">
            <span className="account-avatar" aria-hidden="true">
              <UserRound size={20} strokeWidth={2.4} />
            </span>
            <div>
              <span>Checkout contact</span>
              <h2>How should we contact you?</h2>
            </div>
          </div>
          {!orderingCustomer && showAuthRequirement ? <div className="checkout-auth-required" role="status" aria-live="polite"><h2 ref={authRequirementRef} tabIndex="-1">Sign in to place your order</h2><p>Your café bag is saved. Sign in or create a customer account to continue.</p><div className="form-actions"><Link className="primary-button" to="/account/sign-in?returnTo=%2Fcart">Sign In</Link><Link className="secondary-button" to="/account/create?returnTo=%2Fcart">Create Account</Link></div></div> : null}
          <div className="checkout-contact-grid">
            <label>
              <span>Name</span>
              <input
                autoComplete="name"
                disabled={checkoutLocked}
                required
                ref={(input) => { checkoutContactInputsRef.current.name = input; }}
                value={checkoutContact.name}
                onChange={(event) =>
                  updateCheckoutContact("name", event.target.value)
                }
              />
            </label>
            <label>
              <span>Email</span>
              <input
                autoComplete="email"
                disabled={checkoutLocked}
                required
                ref={(input) => { checkoutContactInputsRef.current.email = input; }}
                type="email"
                value={checkoutContact.email}
                onChange={(event) =>
                  updateCheckoutContact("email", event.target.value)
                }
              />
            </label>
            <label>
              <span>Phone</span>
              <input
                autoComplete="tel"
                disabled={checkoutLocked}
                required
                ref={(input) => { checkoutContactInputsRef.current.phone = input; }}
                type="tel"
                value={checkoutContact.phone}
                onChange={(event) =>
                  updateCheckoutContact("phone", formatCustomerPhone(event.target.value))
                }
                inputMode="numeric"
                pattern="\(\d{3}\) \d{3}-\d{4}"
              />
            </label>
          </div>
        </div>
        <label className="order-notes-field">
          <span>Order notes</span>
          <textarea
            maxLength={2000}
            disabled={checkoutLocked}
            placeholder="Milk preference, pastry warming, or pickup notes"
            rows={3}
            value={orderNotes}
            onChange={(event) => updateOrderNotes(event.target.value)}
          />
        </label>
        <div className="cart-total-row cart-pricing-breakdown">
          <span>Subtotal</span>
          <strong>{formatPrice(orderPricing.subtotalCents / 100)}</strong>
          <span>{formatTaxLabel(catalog.pricing)}</span>
          <strong>{formatPrice(orderPricing.taxCents / 100)}</strong>
          <span>Estimated Total</span>
          <strong>{formatPrice(orderPricing.totalCents / 100)}</strong>
        </div>
        {!schedule?.ordering_available && schedule?.unavailable_reason ? (
          <p className="form-status checkout-error" role="alert">{schedule.unavailable_reason}</p>
        ) : scheduleError ? (
          <p className="form-status checkout-error" role="alert">{scheduleError}</p>
        ) : checkoutError ? (
          <p className="form-status checkout-error" role="alert">
            {checkoutError}
          </p>
        ) : null}
        {resolvedCart.hasStaleLines ? (
          <Link className="primary-button" to="/menu">
            Update order
          </Link>
        ) : (
          <button
            aria-busy={isPlacingOrder}
            className="primary-button"
            disabled={isPlacingOrder || scheduleStatus !== "ready" || !schedule?.ordering_available || !selectedPickup}
            type="button"
            onClick={placeOrder}
          >
            <ClipboardList size={17} strokeWidth={2.4} />
            {isPlacingOrder ? "Placing order…" : "Place order"}
          </button>
        )}
      </div>
    </section>
  );
}
