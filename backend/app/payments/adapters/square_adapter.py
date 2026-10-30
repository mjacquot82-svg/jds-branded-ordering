"""Square adapter behind the provider-neutral payment port."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.orders.constants import OrderStatus
from app.orders.models import Order
from app.payments.errors import PaymentCheckoutError, ProviderNotConnectedError
from app.payments.order_payment import (
    PAYMENT_STATUS_FAILED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PENDING,
    PAYMENT_STATUS_UNPAID,
)
from app.payments.port import (
    CheckoutSession,
    ConnectionStatus,
    NormalizedPaymentEvent,
    PaymentStatusResult,
    RefundResult,
    ReturnUrls,
)
from app.square.client import SquareApiError
from app.square.config import SquareConfigurationError, SquareSettings
from app.square.models import SquareInstallation
from app.square.security import verify_square_signature
from app.square.service import SquareNotConnected, start_checkout

logger = logging.getLogger(__name__)


def _settings() -> SquareSettings | None:
    settings = SquareSettings.from_env()
    return settings if settings.is_configured else None


class SquarePaymentProvider:
    key = "square"

    def connection_status(self, session: Session, organization_id: UUID) -> ConnectionStatus:
        settings = _settings()
        installation = None
        if settings is not None:
            installation = session.scalar(
                select(SquareInstallation).where(
                    SquareInstallation.organization_id == organization_id,
                    SquareInstallation.environment == settings.environment,
                )
            )
        health = "disconnected"
        connected = False
        if installation is not None:
            if installation.connection_state != "connected":
                health = "reconnect_required"
            elif not installation.location_id:
                health = "no_location"
            else:
                health = "healthy"
                connected = True
        return ConnectionStatus(
            connected=connected,
            provider=self.key,
            display_hint=(
                "Square connected — customers can pay."
                if connected
                else "Connect Square to accept payments."
            ),
            environment=settings.environment if settings else None,
            health=health,
            details={
                "installation_present": installation is not None,
                "platform_configured": settings is not None,
            },
        )

    def create_checkout(
        self, session: Session, order: Order, *, return_urls: ReturnUrls | None = None,
    ) -> CheckoutSession:
        settings = _settings()
        if settings is None:
            raise ProviderNotConnectedError("Square payments are not set up on this platform.")
        now = datetime.now(timezone.utc)
        if order.status == OrderStatus.PAID:
            raise PaymentCheckoutError("Order is already paid.", code="order_already_paid")
        if order.expires_at <= now:
            raise PaymentCheckoutError("Order has expired.", code="order_expired")
        # Reuse the open link so one JDS order never maps to two Square orders.
        if (
            order.payment_provider == self.key
            and order.payment_checkout_ref
            and order.payment_redirect_url
            and order.status == OrderStatus.PAYMENT_PENDING
        ):
            return CheckoutSession(
                provider=self.key, provider_ref=order.payment_checkout_ref,
                redirect_url=order.payment_redirect_url, expires_at=order.payment_expires_at,
            )
        try:
            start_checkout(session, settings, order)
        except SquareNotConnected as error:
            raise ProviderNotConnectedError(str(error)) from error
        except SquareApiError as error:
            logger.error("Square checkout failed code=%s order=%s", error.code, order.id)
            raise PaymentCheckoutError(
                "Secure payment could not be started. Please try again.", code=error.code
            ) from error
        except (TypeError, ValueError) as error:
            raise PaymentCheckoutError(
                "Payment is temporarily unavailable. Please try again.",
                code="checkout_configuration_error",
            ) from error
        return CheckoutSession(
            provider=self.key,
            provider_ref=order.payment_checkout_ref or "",
            redirect_url=order.payment_redirect_url,
            expires_at=order.payment_expires_at,
        )

    def reconcile(self, session: Session, order: Order) -> PaymentStatusResult:
        status_map = {
            OrderStatus.PAID: PAYMENT_STATUS_PAID,
            OrderStatus.PAYMENT_PENDING: PAYMENT_STATUS_PENDING,
            OrderStatus.PAYMENT_FAILED: PAYMENT_STATUS_FAILED,
            OrderStatus.PENDING: PAYMENT_STATUS_UNPAID,
        }
        return PaymentStatusResult(
            status=order.payment_status or status_map.get(order.status, PAYMENT_STATUS_UNPAID),
            provider=self.key,
            provider_txn_ref=order.payment_provider_txn_id,
            amount_cents=order.total_cents,
            currency=order.currency,
            paid_at=order.payment_paid_at,
            failure_code=order.payment_failure_code,
        )

    def handle_webhook(
        self, session: Session, *, headers: dict[str, str], body: bytes,
    ) -> list[NormalizedPaymentEvent]:
        """Verify signature and normalize. Persistence lives in the /square/webhooks route."""
        settings = _settings()
        if settings is None:
            raise SquareConfigurationError("Square is not configured.")
        lowered = {k.lower(): v for k, v in headers.items()}
        verify_square_signature(
            body, lowered.get("x-square-hmacsha256-signature"),
            settings.webhook_url, settings.webhook_signature_key,
        )
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("Square webhook payload must be an object.")
        event_type = str(payload.get("type") or "")
        payment = ((payload.get("data") or {}).get("object") or {}).get("payment") or {}
        status = str(payment.get("status") or "").upper()
        normalized = "payment.updated"
        if event_type.startswith("payment.") and status == "COMPLETED":
            normalized = "payment.succeeded"
        elif event_type.startswith("payment.") and status in {"FAILED", "CANCELED"}:
            normalized = "payment.failed"
        elif not event_type.startswith("payment."):
            normalized = f"square.{event_type}"
        return [
            NormalizedPaymentEvent(
                type=normalized,
                provider=self.key,
                provider_payment_ref=str(payment["id"]) if payment.get("id") else None,
                raw_event_id=str(payload.get("event_id") or "") or None,
                payload={
                    "merchant_id": payload.get("merchant_id"),
                    "square_order_id": payment.get("order_id"),
                    "reported_status": status,
                    "event_type": event_type,
                },
            )
        ]

    def refund(self, session: Session, order: Order, amount_cents: int | None = None) -> RefundResult:
        raise PaymentCheckoutError(
            "Square refunds are not available in the app yet.",
            code="payment_refund_not_implemented",
        )
