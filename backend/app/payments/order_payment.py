"""Provider-neutral order payment field helpers (dual-write with Clover columns)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.orders.constants import OrderStatus
from app.orders.models import Order

# Electronic payment lifecycle on the order (independent of Order.status).
PAYMENT_STATUS_UNPAID = "unpaid"
PAYMENT_STATUS_PENDING = "pending"
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_FAILED = "failed"
PAYMENT_STATUS_CANCELLED = "cancelled"
PAYMENT_STATUS_REFUNDED = "refunded"
PAYMENT_STATUS_MANUAL = "manual_unpaid"


def sync_checkout_started(
    order: Order,
    *,
    provider: str,
    checkout_ref: str,
    redirect_url: str,
    expires_at: datetime,
    installation_id: UUID | None = None,
    provider_metadata: dict[str, Any] | None = None,
) -> None:
    """Record an electronic checkout session on the order (generic + Clover dual-write)."""
    order.payment_provider = provider
    order.payment_status = PAYMENT_STATUS_PENDING
    order.payment_checkout_ref = checkout_ref
    order.payment_redirect_url = redirect_url
    order.payment_expires_at = expires_at
    order.payment_failure_code = None
    if provider_metadata is not None:
        order.payment_provider_metadata = provider_metadata
    if provider == "clover":
        # Dual-write legacy Clover columns for existing webhook/reconcile paths.
        if installation_id is not None:
            order.clover_installation_id = installation_id
        order.clover_checkout_session_id = checkout_ref
        order.clover_checkout_url = redirect_url
        order.clover_checkout_expires_at = expires_at
        if provider_metadata:
            if provider_metadata.get("environment"):
                order.clover_environment = str(provider_metadata["environment"])
            if provider_metadata.get("merchant_id"):
                order.clover_merchant_id = str(provider_metadata["merchant_id"])


def mark_electronically_paid(
    order: Order,
    *,
    provider_txn_ref: str | None,
    paid_at: datetime | None = None,
) -> None:
    order.status = OrderStatus.PAID
    order.payment_status = PAYMENT_STATUS_PAID
    order.payment_provider_txn_id = provider_txn_ref
    order.payment_paid_at = paid_at or datetime.now(timezone.utc)
    order.payment_failure_code = None


def mark_electronic_payment_failed(
    order: Order,
    *,
    failure_code: str | None = None,
) -> None:
    if order.status == OrderStatus.PAID:
        return
    order.status = OrderStatus.PAYMENT_FAILED
    order.payment_status = PAYMENT_STATUS_FAILED
    order.payment_failure_code = failure_code


def assert_not_false_paid(order: Order) -> None:
    """Unpaid / manual must never look electronically paid."""
    if order.payment_status in {PAYMENT_STATUS_MANUAL, PAYMENT_STATUS_UNPAID, None}:
        if order.status == OrderStatus.PAID and not order.payment_provider_txn_id:
            raise ValueError("Manual/unpaid orders must not be marked electronically paid.")
