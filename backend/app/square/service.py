"""Square connection, checkout, and verified payment logic shared by adapter and routes."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.orders.constants import OrderStatus
from app.orders.models import Order
from app.orders.reference import order_reference
from app.payments.order_payment import mark_electronically_paid, sync_checkout_started
from app.square.client import SquareApiError, SquareClient
from app.square.config import SquareSettings
from app.square.models import SquareInstallation
from app.square.security import SquareTokenCipher

logger = logging.getLogger(__name__)

PROVIDER_KEY = "square"
# Square access tokens last 30 days; refresh well before that.
REFRESH_WINDOW = timedelta(days=7)


class SquareNotConnected(RuntimeError):
    pass


def connected_installation(
    session: Session, organization_id: UUID, environment: str, *, for_update: bool = False
) -> SquareInstallation | None:
    query = select(SquareInstallation).where(
        SquareInstallation.organization_id == organization_id,
        SquareInstallation.environment == environment,
        SquareInstallation.connection_state == "connected",
    )
    if for_update:
        query = query.with_for_update()
    return session.scalar(query)


def active_access_token(
    session: Session, settings: SquareSettings, installation: SquareInstallation,
    *, client: SquareClient | None = None, now: datetime | None = None,
) -> str:
    """Decrypt the token, refreshing it first if it is close to expiry."""
    client = client or SquareClient(settings)
    cipher = SquareTokenCipher(settings.token_encryption_key)
    now = now or datetime.now(timezone.utc)
    if installation.access_token_expires_at - now > REFRESH_WINDOW:
        return cipher.decrypt(installation.access_token_encrypted)
    try:
        pair = client.refresh_access_token(cipher.decrypt(installation.refresh_token_encrypted))
    except SquareApiError as error:
        if error.status_code in {400, 401}:
            installation.connection_state = "reconnect_required"
            installation.reconnect_reason = "refresh_rejected"
            session.flush()
            raise SquareNotConnected("Square connection needs to be reconnected.") from error
        raise
    if pair.merchant_id != installation.merchant_id:
        raise SquareNotConnected("Square refresh returned a different seller.")
    installation.access_token_encrypted = cipher.encrypt(pair.access_token)
    installation.refresh_token_encrypted = cipher.encrypt(pair.refresh_token)
    installation.access_token_expires_at = pair.expires_at
    session.flush()
    return pair.access_token


def pick_location(locations: list[dict[str, Any]]) -> dict[str, Any] | None:
    """First active location that can take cards; else first active location."""
    active = [loc for loc in locations if str(loc.get("status", "")).upper() == "ACTIVE"]
    for loc in active:
        if "CREDIT_CARD_PROCESSING" in (loc.get("capabilities") or []):
            return loc
    return active[0] if active else None


def payment_link_payload(order: Order, installation: SquareInstallation, settings: SquareSettings) -> dict:
    if installation.currency and installation.currency != order.currency:
        raise ValueError("Order currency does not match the Square location currency.")
    if order.total_cents <= 0:
        raise ValueError("Order total must be positive for Square checkout.")
    reference = order_reference(order)
    return_url = (
        f"{settings.frontend_url.rstrip('/')}/confirmation"
        f"?order={order.public_access_token}&payment=success&provider=square"
    )
    payload: dict[str, Any] = {
        # Same order version → same link (Square dedupes on this key).
        "idempotency_key": f"jds-{order.public_access_token}-v{order.version}",
        # quick_pay charges our already-computed total, so tax is never recomputed by Square.
        "quick_pay": {
            "name": f"Order {reference}",
            "price_money": {"amount": int(order.total_cents), "currency": order.currency},
            "location_id": installation.location_id,
        },
        "checkout_options": {"redirect_url": return_url, "ask_for_shipping_address": False},
        "payment_note": f"JDS order {reference}",
    }
    if (order.guest_email or "").strip():
        payload["pre_populated_data"] = {"buyer_email": order.guest_email.strip()}
    return payload


def start_checkout(
    session: Session, settings: SquareSettings, order: Order, *, client: SquareClient | None = None,
) -> None:
    client = client or SquareClient(settings)
    installation = connected_installation(session, order.organization_id, settings.environment)
    if installation is None or not installation.location_id:
        raise SquareNotConnected("Square is not connected for this business.")
    token = active_access_token(session, settings, installation, client=client)
    link = client.create_payment_link(token, payment_link_payload(order, installation, settings))
    sync_checkout_started(
        order,
        provider=PROVIDER_KEY,
        checkout_ref=str(link["order_id"]),
        redirect_url=str(link["url"]),
        expires_at=order.expires_at,
        provider_metadata={
            "environment": installation.environment,
            "merchant_id": installation.merchant_id,
            "location_id": installation.location_id,
            "installation_id": str(installation.id),
            "payment_link_id": str(link.get("id") or ""),
        },
    )
    order.status = OrderStatus.PAYMENT_PENDING
    order.version += 1
    session.flush()


def verify_payment_matches(payment: dict[str, Any], order: Order, installation: SquareInstallation) -> str | None:
    """Return None if this Square payment proves the order is paid, else a reason."""
    if str(payment.get("status", "")).upper() != "COMPLETED":
        return "payment_not_completed"
    if payment.get("order_id") != order.payment_checkout_ref:
        return "order_mismatch"
    if installation.location_id and payment.get("location_id") != installation.location_id:
        return "location_mismatch"
    money = payment.get("amount_money") or {}
    if money.get("amount") != order.total_cents or money.get("currency") != order.currency:
        return "amount_mismatch"
    return None


def apply_verified_payment(
    session: Session, settings: SquareSettings, installation: SquareInstallation, order: Order,
    payment_id: str, *, client: SquareClient | None = None,
) -> tuple[bool, str]:
    """Re-fetch the payment from Square (never trust webhook bodies) and mark paid if it matches.

    Returns (newly_paid, outcome).
    """
    if order.status == OrderStatus.PAID:
        return False, "already_paid"
    client = client or SquareClient(settings)
    token = active_access_token(session, settings, installation, client=client)
    payment = client.get_payment(token, payment_id)
    reason = verify_payment_matches(payment, order, installation)
    if reason:
        return False, reason
    paid_at = None
    if payment.get("updated_at"):
        try:
            paid_at = datetime.fromisoformat(str(payment["updated_at"]).replace("Z", "+00:00"))
        except ValueError:
            paid_at = None
    mark_electronically_paid(order, provider_txn_ref=str(payment["id"]), paid_at=paid_at)
    order.version += 1
    session.flush()
    return True, "paid_transition_applied"


def reconcile_from_square_order(
    session: Session, settings: SquareSettings, order: Order, *, client: SquareClient | None = None,
) -> tuple[bool, str]:
    """Status check: look up the Square order behind the link and verify any tender."""
    if order.payment_provider != PROVIDER_KEY or not order.payment_checkout_ref:
        return False, "not_square_checkout"
    if order.status == OrderStatus.PAID:
        return False, "already_paid"
    installation = connected_installation(session, order.organization_id, settings.environment)
    if installation is None:
        return False, "not_connected"
    client = client or SquareClient(settings)
    token = active_access_token(session, settings, installation, client=client)
    square_order = client.get_order(token, order.payment_checkout_ref)
    for tender in square_order.get("tenders") or []:
        payment_id = tender.get("payment_id") or tender.get("id")
        if payment_id:
            newly_paid, outcome = apply_verified_payment(
                session, settings, installation, order, str(payment_id), client=client
            )
            if newly_paid:
                return True, outcome
    return False, "no_completed_payment"


class SquareRefundError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def refund_idempotency_key(order: Order) -> str:
    # One full refund per order: retries and double-clicks reuse the same Square refund.
    import hashlib

    digest = hashlib.sha256(order.public_access_token.encode()).hexdigest()[:40]
    return f"jdsr-{digest}"  # Square caps idempotency keys at 45 chars


def refund_order(
    session: Session, settings: SquareSettings, order: Order, *,
    client: SquareClient | None = None, now: datetime | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Fully refund a paid Square order with the shop's own token.

    Returns (newly_refunded, refund_metadata). Idempotent: an already refunded
    order returns its stored refund without calling Square again.
    """
    from app.payments.order_payment import PAYMENT_STATUS_PAID, PAYMENT_STATUS_REFUNDED

    metadata = dict(order.payment_provider_metadata or {})
    if order.payment_status == PAYMENT_STATUS_REFUNDED:
        return False, metadata.get("refund") or {}
    if order.payment_provider != PROVIDER_KEY or not order.payment_provider_txn_id:
        raise SquareRefundError("not_square_payment", "Only orders paid online with Square can be refunded here.")
    if order.status != OrderStatus.PAID or order.payment_status != PAYMENT_STATUS_PAID:
        raise SquareRefundError("not_paid", "Only paid orders can be refunded.")
    environment = metadata.get("environment") or settings.environment
    if environment != settings.environment:
        raise SquareRefundError("environment_mismatch", "This order was paid in a different Square mode.")
    installation = connected_installation(session, order.organization_id, settings.environment)
    if installation is None:
        raise SquareNotConnected("Square is not connected for this business.")
    if metadata.get("merchant_id") and metadata["merchant_id"] != installation.merchant_id:
        raise SquareRefundError("merchant_mismatch", "This order was paid to a different Square account.")
    client = client or SquareClient(settings)
    token = active_access_token(session, settings, installation, client=client)
    refund = client.refund_payment(token, {
        "idempotency_key": refund_idempotency_key(order),
        "payment_id": order.payment_provider_txn_id,
        "amount_money": {"amount": int(order.total_cents), "currency": order.currency},
        "reason": f"Refund for JDS order {order_reference(order)}",
    })
    refund_status = str(refund.get("status") or "").upper()
    if refund_status in {"REJECTED", "FAILED"}:
        raise SquareRefundError("refund_rejected", "Square declined this refund. Check the order in Square.")
    record = {
        "id": str(refund["id"]),
        "status": refund_status.lower() or "pending",
        "amount_cents": int(order.total_cents),
        "currency": order.currency,
        "refunded_at": (now or datetime.now(timezone.utc)).isoformat(),
    }
    metadata["refund"] = record
    order.payment_provider_metadata = metadata
    order.payment_status = PAYMENT_STATUS_REFUNDED
    order.version += 1
    session.flush()
    return True, record
