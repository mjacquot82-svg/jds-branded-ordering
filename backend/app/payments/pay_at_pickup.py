"""Pay at pickup (manual, non-electronic payment).

Rules (docs/MANUAL_AND_PAY_AT_PICKUP.md):
- Never looks electronically paid: payment_status=manual_unpaid, no provider,
  no provider txn id, no provider checkout/webhook.
- Staff record the money at the counter with an explicit action that writes an
  audit row. A no-show cancels the order and blocks pay at pickup for that
  customer at this shop.
- Off by default per shop. When on: verified email, >= N completed orders,
  order total <= max, and not blocked by a previous no-show.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.jds_auth.models import JdsUser
from app.orders.constants import FulfillmentStatus, OrderStatus
from app.orders.models import Order
from app.payments.models import OrganizationOrderSettings, PayAtPickupBlock
from app.payments.order_payment import (
    PAYMENT_STATUS_CANCELLED,
    PAYMENT_STATUS_MANUAL,
    PAYMENT_STATUS_PAID,
)
from app.platform.models import OperationalAuditEvent

PAY_AT_PICKUP_METHOD = "pay_at_pickup"
DEFAULT_MIN_COMPLETED_ORDERS = 1
DEFAULT_MAX_TOTAL_CENTS = 2500
# A pay-at-pickup order stays valid until the end of its pickup window plus a
# grace period, instead of the 30-minute electronic checkout expiry.
PICKUP_GRACE = timedelta(hours=12)


class PayAtPickupError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OrderSettingsView:
    pay_at_pickup_enabled: bool
    pay_at_pickup_min_completed_orders: int
    pay_at_pickup_max_total_cents: int
    new_order_alert_email: str | None


@dataclass(frozen=True)
class Eligibility:
    available: bool
    reason: str | None
    max_total_cents: int
    min_completed_orders: int
    completed_orders: int


def get_order_settings(session: Session, organization_id: UUID) -> OrderSettingsView:
    row = session.get(OrganizationOrderSettings, organization_id)
    if row is None:
        return OrderSettingsView(False, DEFAULT_MIN_COMPLETED_ORDERS, DEFAULT_MAX_TOTAL_CENTS, None)
    return OrderSettingsView(
        bool(row.pay_at_pickup_enabled),
        row.pay_at_pickup_min_completed_orders,
        row.pay_at_pickup_max_total_cents,
        row.new_order_alert_email,
    )


def update_order_settings(
    session: Session,
    organization_id: UUID,
    *,
    pay_at_pickup_enabled: bool,
    pay_at_pickup_min_completed_orders: int,
    pay_at_pickup_max_total_cents: int,
    new_order_alert_email: str | None,
) -> OrderSettingsView:
    row = session.get(OrganizationOrderSettings, organization_id)
    if row is None:
        row = OrganizationOrderSettings(organization_id=organization_id)
        session.add(row)
    row.pay_at_pickup_enabled = pay_at_pickup_enabled
    row.pay_at_pickup_min_completed_orders = pay_at_pickup_min_completed_orders
    row.pay_at_pickup_max_total_cents = pay_at_pickup_max_total_cents
    row.new_order_alert_email = (new_order_alert_email or "").strip() or None
    session.flush()
    return get_order_settings(session, organization_id)


def completed_order_count(session: Session, organization_id: UUID, user_id: UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(Order)
            .where(
                Order.organization_id == organization_id,
                Order.customer_user_id == user_id,
                Order.status == OrderStatus.PAID,
                Order.fulfillment_status == FulfillmentStatus.COMPLETED,
            )
        )
        or 0
    )


def is_blocked(session: Session, organization_id: UUID, user_id: UUID) -> bool:
    return (
        session.scalar(
            select(PayAtPickupBlock.id).where(
                PayAtPickupBlock.organization_id == organization_id,
                PayAtPickupBlock.customer_user_id == user_id,
            )
        )
        is not None
    )


def check_eligibility(
    session: Session,
    organization_id: UUID,
    user_id: UUID,
    *,
    total_cents: int | None,
) -> Eligibility:
    settings = get_order_settings(session, organization_id)
    completed = 0

    def result(reason: str | None) -> Eligibility:
        return Eligibility(
            available=reason is None,
            reason=reason,
            max_total_cents=settings.pay_at_pickup_max_total_cents,
            min_completed_orders=settings.pay_at_pickup_min_completed_orders,
            completed_orders=completed,
        )

    if not settings.pay_at_pickup_enabled:
        return result("not_offered")
    user = session.get(JdsUser, user_id)
    if user is None or user.status != "active" or user.email_verified_at is None:
        return result("email_not_verified")
    if is_blocked(session, organization_id, user_id):
        return result("blocked_after_no_show")
    completed = completed_order_count(session, organization_id, user_id)
    if completed < settings.pay_at_pickup_min_completed_orders:
        return result("not_enough_completed_orders")
    if total_cents is not None and total_cents > settings.pay_at_pickup_max_total_cents:
        return result("order_total_too_high")
    return result(None)


def _audit(session: Session, order: Order, *, action: str, actor_user_id: UUID | None, metadata: dict) -> None:
    session.add(
        OperationalAuditEvent(
            organization_id=order.organization_id,
            scope="tenant",
            actor_user_id=actor_user_id,
            action=action,
            target_type="order",
            target_id=str(order.id),
            outcome="success",
            metadata_json=metadata,
        )
    )


def is_pay_at_pickup(order: Order) -> bool:
    return order.payment_status == PAYMENT_STATUS_MANUAL or (
        (order.payment_provider_metadata or {}).get("method") == PAY_AT_PICKUP_METHOD
    )


def accept_pay_at_pickup(
    session: Session,
    order: Order,
    *,
    customer_user_id: UUID,
    now: datetime | None = None,
) -> Order:
    """Turn a freshly created pending order into a pay-at-pickup order."""
    now = now or datetime.now(timezone.utc)
    if order.payment_status == PAYMENT_STATUS_MANUAL and order.status == OrderStatus.PAYMENT_PENDING:
        return order  # idempotent retry
    if order.status != OrderStatus.PENDING or order.payment_status not in {None, "unpaid"}:
        raise PayAtPickupError("order_not_pending", "This order can no longer switch to pay at pickup.")
    if order.payment_checkout_ref or order.clover_checkout_session_id:
        raise PayAtPickupError("order_not_pending", "Online payment was already started for this order.")
    expires_at = order.expires_at if order.expires_at.tzinfo else order.expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise PayAtPickupError("order_expired", "This order expired. Please place it again.")
    eligibility = check_eligibility(
        session, order.organization_id, customer_user_id, total_cents=order.total_cents
    )
    if not eligibility.available:
        raise PayAtPickupError(eligibility.reason or "not_offered", "Pay at pickup isn't available for this order.")
    order.status = OrderStatus.PAYMENT_PENDING
    order.payment_status = PAYMENT_STATUS_MANUAL
    order.payment_provider = None
    order.payment_provider_txn_id = None
    order.payment_provider_metadata = {"method": PAY_AT_PICKUP_METHOD}
    pickup = order.requested_pickup_at if order.requested_pickup_at.tzinfo else order.requested_pickup_at.replace(tzinfo=timezone.utc)
    order.expires_at = max(expires_at, pickup + PICKUP_GRACE)
    order.version += 1
    _audit(session, order, action="order.pay_at_pickup.accepted", actor_user_id=customer_user_id,
           metadata={"total_cents": order.total_cents})
    return order


def mark_collected_at_counter(
    session: Session, order: Order, *, actor_user_id: UUID, expected_version: int, now: datetime | None = None
) -> Order:
    """Staff record cash/card taken at the counter. No provider, no txn id."""
    if not is_pay_at_pickup(order):
        raise PayAtPickupError("not_pay_at_pickup", "Only pay-at-pickup orders can be marked as paid here.")
    if order.status == OrderStatus.PAID:
        return order
    if order.fulfillment_status == FulfillmentStatus.CANCELLED:
        raise PayAtPickupError("order_cancelled", "This order was cancelled.")
    if expected_version != order.version:
        raise PayAtPickupError("stale_order", "This order changed on another device. Refresh and try again.")
    now = now or datetime.now(timezone.utc)
    order.status = OrderStatus.PAID
    order.payment_status = PAYMENT_STATUS_PAID
    order.payment_provider = None
    order.payment_provider_txn_id = None
    order.payment_paid_at = now
    order.payment_provider_metadata = {"method": PAY_AT_PICKUP_METHOD, "collected_by_staff": True}
    order.version += 1
    _audit(session, order, action="order.pay_at_pickup.collected", actor_user_id=actor_user_id,
           metadata={"total_cents": order.total_cents})
    return order


def mark_no_show(
    session: Session, order: Order, *, actor_user_id: UUID, expected_version: int, now: datetime | None = None
) -> Order:
    """Cancel an unpaid pay-at-pickup order and block the customer from pay at pickup."""
    if not is_pay_at_pickup(order) or order.status == OrderStatus.PAID:
        raise PayAtPickupError("not_unpaid_pay_at_pickup", "Only unpaid pay-at-pickup orders can be marked as a no-show.")
    if order.fulfillment_status == FulfillmentStatus.CANCELLED:
        return order
    if expected_version != order.version:
        raise PayAtPickupError("stale_order", "This order changed on another device. Refresh and try again.")
    now = now or datetime.now(timezone.utc)
    order.fulfillment_status = FulfillmentStatus.CANCELLED
    order.cancelled_at = now
    order.fulfillment_updated_at = now
    order.payment_status = PAYMENT_STATUS_CANCELLED
    order.payment_provider_metadata = {"method": PAY_AT_PICKUP_METHOD, "no_show": True}
    order.version += 1
    if order.customer_user_id is not None and not is_blocked(session, order.organization_id, order.customer_user_id):
        session.add(PayAtPickupBlock(
            organization_id=order.organization_id,
            customer_user_id=order.customer_user_id,
            order_id=order.id,
            reason="no_show",
        ))
    _audit(session, order, action="order.pay_at_pickup.no_show", actor_user_id=actor_user_id,
           metadata={"total_cents": order.total_cents})
    return order


def clear_block(session: Session, organization_id: UUID, user_id: UUID) -> bool:
    row = session.scalar(select(PayAtPickupBlock).where(
        PayAtPickupBlock.organization_id == organization_id,
        PayAtPickupBlock.customer_user_id == user_id,
    ))
    if row is None:
        return False
    session.delete(row)
    return True
