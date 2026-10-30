"""JDS-branded receipt email to the customer when an order is placed.

Sent once when a pay-at-pickup order is confirmed or a card order becomes paid.
Fail-safe like owner alerts: anything missing or failing is logged and swallowed,
so the customer's order is never affected.

Configuration (both required; without them receipts are skipped and logged):
  JDS_ORDER_ALERT_RESEND_API_KEY  Resend API key (sending only), shared with owner alerts
  JDS_ORDER_ALERT_FROM_EMAIL      verified sender, e.g. contact@jdsstudio.ca
Optional:
  JDS_CUSTOMER_RECEIPTS_ENABLED   set "false" to stop receipts (default on)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.communications import order_alerts
from app.communications.order_alerts import AlertEmail
from app.orders.models import Order
from app.orders.reference import order_reference

logger = logging.getLogger(__name__)


def customer_receipts_enabled() -> bool:
    if os.environ.get("JDS_CUSTOMER_RECEIPTS_ENABLED", "true").strip().lower() == "false":
        return False
    return bool(
        os.environ.get("JDS_ORDER_ALERT_RESEND_API_KEY", "").strip()
        and os.environ.get("JDS_ORDER_ALERT_FROM_EMAIL", "").strip()
    )


def _money(cents: int, currency: str) -> str:
    return f"${cents / 100:,.2f} {currency}"


def _pickup_time(order: Order) -> str:
    try:
        local = order.requested_pickup_at.astimezone(ZoneInfo(order.business_timezone))
    except Exception:  # noqa: BLE001
        local = order.requested_pickup_at
    return local.strftime("%A, %B %-d at %-I:%M %p")


def _is_pay_at_pickup(order: Order) -> bool:
    from app.payments.pay_at_pickup import is_pay_at_pickup

    return is_pay_at_pickup(order)


def build_customer_receipt(order: Order, *, shop_name: str) -> AlertEmail:
    reference = order_reference(order)
    pay_at_pickup = _is_pay_at_pickup(order)
    payment_line = (
        f"Payment: Pay at pickup - please pay {_money(order.total_cents, order.currency)} at the counter."
        if pay_at_pickup
        else "Payment: Paid online by card."
    )
    lines = [
        f"Thanks for your order from {shop_name}!",
        "",
        f"Order number: {reference}",
        f"Pickup: {_pickup_time(order)}",
        payment_line,
        "",
        "Your order:",
    ]
    for item in order.items:
        variant = f" ({item.variant_name})" if item.variant_name else ""
        lines.append(f"- {item.quantity} x {item.product_name}{variant}  {_money(item.line_subtotal_cents, order.currency)}")
        for modifier in item.modifiers:
            lines.append(f"    + {modifier.modifier_option_name}")
    if order.notes:
        lines += ["", f"Notes: {order.notes}"]
    lines += [
        "",
        f"Subtotal: {_money(order.subtotal_cents, order.currency)}",
        f"Tax: {_money(order.tax_cents, order.currency)}",
        f"Total: {_money(order.total_cents, order.currency)}",
        "",
        f"Show order number {reference} at the counter when you pick up.",
        "",
        "Sent by JDS Studio on behalf of " + shop_name + ".",
    ]
    subject = f"Your {shop_name} order {reference}" + (" - pay at pickup" if pay_at_pickup else " - receipt")
    return AlertEmail(to=order.guest_email, subject=subject, text="\n".join(lines))


def _shop_name(session: Session, order: Order) -> str:
    from app.jds_auth.models import Organization
    from app.platform.models import BusinessProfile

    profile = session.get(BusinessProfile, order.organization_id)
    if profile is not None and (profile.display_name or "").strip():
        return profile.display_name.strip()
    organization = session.get(Organization, order.organization_id)
    return organization.name if organization is not None else "your café"


def send_customer_receipt_safely(session: Session, order: Order) -> bool:
    """Returns True if a receipt was handed to the provider. Never raises."""
    try:
        if not customer_receipts_enabled():
            logger.info("customer receipt skipped order=%s reason=not_configured", getattr(order, "id", None))
            return False
        if not (getattr(order, "guest_email", "") or "").strip():
            logger.info("customer receipt skipped order=%s reason=no_email", order.id)
            return False
        order_alerts.email_sender(build_customer_receipt(order, shop_name=_shop_name(session, order)))
        logger.info("customer receipt sent org=%s order=%s", order.organization_id, order.id)
        return True
    except Exception as error:  # noqa: BLE001 - receipts must never break ordering
        logger.warning(
            "customer receipt failed org=%s order=%s error=%s",
            getattr(order, "organization_id", None), getattr(order, "id", None), type(error).__name__,
        )
        return False
