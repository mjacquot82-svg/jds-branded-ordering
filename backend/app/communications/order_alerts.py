"""New-order alert email to the shop.

Fail-safe by design: any problem (not configured, network, provider error,
bad data) is logged and swallowed. The customer's order is never affected.

OFF by default: shops see new orders on the owner Orders screen. Set
JDS_OWNER_ORDER_ALERTS_ENABLED=true to turn these emails on platform-wide.

Configuration (all optional; without them alerts are skipped and logged):
  JDS_OWNER_ORDER_ALERTS_ENABLED  "true" to send owner new-order emails (default false)
  JDS_ORDER_ALERT_RESEND_API_KEY  Resend API key (sending only)
  JDS_ORDER_ALERT_FROM_EMAIL      verified sender, e.g. orders@yourdomain
Recipient: the shop's "new order alert email" in Order settings.
"""

from __future__ import annotations
from app.orders.reference import order_reference

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.orders.models import Order

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


@dataclass(frozen=True)
class AlertEmail:
    to: str
    subject: str
    text: str


def _resend_sender(message: AlertEmail) -> None:
    import httpx

    api_key = os.environ.get("JDS_ORDER_ALERT_RESEND_API_KEY", "").strip()
    sender = os.environ.get("JDS_ORDER_ALERT_FROM_EMAIL", "").strip()
    if not api_key or not sender:
        raise RuntimeError("order_alert_email_not_configured")
    response = httpx.post(
        RESEND_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"from": sender, "to": [message.to], "subject": message.subject, "text": message.text},
        timeout=5.0,
    )
    response.raise_for_status()


# Tests replace this; production uses Resend when configured.
email_sender: Callable[[AlertEmail], None] = _resend_sender


def owner_order_alerts_enabled() -> bool:
    return os.environ.get("JDS_OWNER_ORDER_ALERTS_ENABLED", "false").strip().lower() == "true"


def _money(cents: int, currency: str) -> str:
    return f"${cents / 100:,.2f} {currency}"


def build_new_order_alert(order: Order, *, to: str) -> AlertEmail:
    pay_at_pickup = order.payment_status == "manual_unpaid"
    payment_line = (
        "PAY AT PICKUP - not paid yet. Collect payment at the counter."
        if pay_at_pickup
        else "Paid online."
    )
    lines = [
        f"New order {order_reference(order)}",
        payment_line,
        f"Customer: {order.guest_name} ({order.guest_phone})",
        f"Pickup: {order.requested_pickup_at.isoformat()} ({order.business_timezone})",
        "",
    ]
    for item in order.items:
        variant = f" ({item.variant_name})" if item.variant_name else ""
        lines.append(f"- {item.quantity} x {item.product_name}{variant}")
        for modifier in item.modifiers:
            lines.append(f"    + {modifier.modifier_option_name}")
    if order.notes:
        lines += ["", f"Notes: {order.notes}"]
    lines += ["", f"Total: {_money(order.total_cents, order.currency)}"]
    subject = f"New order {order_reference(order)}" + (" - pay at pickup" if pay_at_pickup else "")
    return AlertEmail(to=to, subject=subject, text="\n".join(lines))


def send_new_order_alert_safely(session: Session, order: Order) -> bool:
    """Returns True if an email was handed to the provider. Never raises."""
    if not owner_order_alerts_enabled():
        logger.info("new-order alert skipped org=%s order=%s reason=disabled", getattr(order, "organization_id", None), getattr(order, "id", None))
        return False
    try:
        from app.payments.pay_at_pickup import get_order_settings

        recipient = get_order_settings(session, order.organization_id).new_order_alert_email
        if not recipient:
            logger.info("new-order alert skipped org=%s order=%s reason=no_recipient", order.organization_id, order.id)
            return False
        email_sender(build_new_order_alert(order, to=recipient))
        logger.info("new-order alert sent org=%s order=%s", order.organization_id, order.id)
        return True
    except Exception as error:  # noqa: BLE001 - alerts must never break ordering
        logger.warning(
            "new-order alert failed org=%s order=%s error=%s",
            getattr(order, "organization_id", None), getattr(order, "id", None), type(error).__name__,
        )
        return False
