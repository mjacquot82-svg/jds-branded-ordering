"""Clover adapter: wraps existing Clover behavior behind the payment port.

Core never imports Clover SDKs. Second providers (Square/Stripe/Moneris) add a
sibling module and register in payments.registry — cart/order/storefront stay put.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.clover.client import CloverApiError, CloverClient
from app.clover.config import CloverConfigurationError, CloverSettings
from app.clover.models import CloverInstallation
from app.clover.security import (
    InvalidWebhookSignature,
    TokenCipher,
    verify_webhook_signature,
)
from app.orders.constants import OrderStatus
from app.orders.models import Order, OrderItem
from app.payments.errors import PaymentCheckoutError, ProviderNotConnectedError
from app.payments.service import ensure_clover_selected_when_connected
from app.payments.order_payment import (
    PAYMENT_STATUS_FAILED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PENDING,
    PAYMENT_STATUS_UNPAID,
    mark_electronically_paid,
    sync_checkout_started,
)
from app.payments.port import (
    CheckoutSession,
    ConnectionStatus,
    NormalizedPaymentEvent,
    PaymentStatusResult,
    RefundResult,
    ReturnUrls,
)

logger = logging.getLogger(__name__)


class CloverPaymentProvider:
    key = "clover"

    def connection_status(
        self, session: Session, organization_id: UUID
    ) -> ConnectionStatus:
        try:
            settings = CloverSettings.from_env()
            settings.validate()
            configured = True
            environment = settings.environment
        except CloverConfigurationError:
            configured = False
            environment = None
            settings = None

        installation = session.scalar(
            select(CloverInstallation).where(
                CloverInstallation.organization_id == organization_id,
                CloverInstallation.connection_state == "connected",
            ).limit(1)
        )
        if environment and installation is not None:
            installation = session.scalar(
                select(CloverInstallation).where(
                    CloverInstallation.organization_id == organization_id,
                    CloverInstallation.environment == environment,
                    CloverInstallation.connection_state == "connected",
                ).limit(1)
            ) or installation

        connected = bool(
            configured
            and installation is not None
            and (
                (settings and settings.ecommerce_private_token)
                or installation.access_token_encrypted
            )
        )
        health = "disconnected"
        if connected and installation is not None:
            now = datetime.now(timezone.utc)
            if installation.connection_state == "reconnect_required":
                health = "reconnect_required"
                connected = False
            elif (
                installation.refresh_token_expires_at is not None
                and installation.refresh_token_expires_at <= now
            ):
                health = "reconnect_required"
                connected = False
            else:
                health = "healthy"

        return ConnectionStatus(
            connected=connected,
            provider=self.key,
            display_hint=(
                "Clover connected — customers can pay."
                if connected
                else "Connect Clover to accept payments."
            ),
            environment=environment or (installation.environment if installation else None),
            health=health,
            details={
                "installation_present": installation is not None,
                "platform_configured": configured,
            },
        )

    def create_checkout(
        self,
        session: Session,
        order: Order,
        *,
        return_urls: ReturnUrls | None = None,
    ) -> CheckoutSession:
        # Delegate to shared implementation used by legacy /clover façade.
        from app.api.v1 import clover as clover_api

        try:
            settings = CloverSettings.from_env()
            settings.validate()
        except CloverConfigurationError as error:
            raise ProviderNotConnectedError(str(error)) from error

        now = datetime.now(timezone.utc)
        if order.status == OrderStatus.PAID:
            raise PaymentCheckoutError(
                "Order is already paid.", code="order_already_paid"
            )
        if order.expires_at <= now:
            raise PaymentCheckoutError("Order has expired.", code="order_expired")

        # Reuse existing active checkout when still valid.
        if (
            order.clover_checkout_url
            and order.clover_checkout_session_id
            and order.clover_checkout_expires_at
            and order.clover_checkout_expires_at > now
        ):
            if not order.payment_checkout_ref:
                sync_checkout_started(
                    order,
                    provider=self.key,
                    checkout_ref=order.clover_checkout_session_id,
                    redirect_url=order.clover_checkout_url,
                    expires_at=order.clover_checkout_expires_at,
                    installation_id=order.clover_installation_id,
                    provider_metadata={
                        "environment": order.clover_environment,
                        "merchant_id": order.clover_merchant_id,
                    },
                )
            return CheckoutSession(
                provider=self.key,
                provider_ref=order.clover_checkout_session_id,
                redirect_url=order.clover_checkout_url,
                expires_at=order.clover_checkout_expires_at,
            )

        installation, access_token = clover_api._active_credential(
            session,
            settings,
            organization_id=order.organization_id,
            installation_id=order.clover_installation_id,
        )
        # Ensure items loaded for payload.
        if not order.items:
            order = session.scalar(
                select(Order)
                .options(selectinload(Order.items).selectinload(OrderItem.modifiers))
                .where(
                    Order.id == order.id,
                    Order.organization_id == order.organization_id,
                )
            ) or order

        try:
            result = CloverClient(settings).create_checkout(
                access_token=access_token,
                merchant_id=installation.merchant_id,
                payload=clover_api._checkout_payload(
                    order,
                    settings,
                    page_config_uuid=installation.page_config_uuid,
                ),
            )
            expires_at = (
                clover_api._parse_clover_checkout_expiration(result.get("expirationTime"))
                if result.get("expirationTime")
                else now + timedelta(minutes=15)
            )
            if expires_at <= now:
                raise ValueError("Clover returned an expired checkout session.")

            sync_checkout_started(
                order,
                provider=self.key,
                checkout_ref=result["checkoutSessionId"],
                redirect_url=result["href"],
                expires_at=expires_at,
                installation_id=installation.id,
                provider_metadata={
                    "environment": installation.environment,
                    "merchant_id": installation.merchant_id,
                },
            )
            order.clover_installation_id = installation.id
            order.clover_environment = installation.environment
            order.clover_merchant_id = installation.merchant_id
            order.status = OrderStatus.PAYMENT_PENDING
            order.version += 1
            ensure_clover_selected_when_connected(session, order.organization_id)
            session.flush()
        except CloverApiError as error:
            logger.error(
                "Clover checkout failed via payment port: code=%s order=%s",
                error.code,
                order.id,
            )
            raise PaymentCheckoutError(
                "Secure payment could not be started. Please try again.",
                code=error.code,
            ) from error
        except (TypeError, ValueError) as error:
            raise PaymentCheckoutError(
                "Payment is temporarily unavailable. Please try again.",
                code="checkout_configuration_error",
            ) from error

        return CheckoutSession(
            provider=self.key,
            provider_ref=order.payment_checkout_ref or order.clover_checkout_session_id or "",
            redirect_url=order.payment_redirect_url or order.clover_checkout_url,
            expires_at=order.payment_expires_at or order.clover_checkout_expires_at,
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
        self,
        session: Session,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> list[NormalizedPaymentEvent]:
        """Validate + parse only; persistence remains in the Clover façade for M1.

        Adapters own signature validation and event semantics. Core receives
        normalized events — the existing /clover/webhooks route still performs
        tenant resolution, idempotency, and order updates, then can emit these.
        """
        try:
            settings = CloverSettings.from_env()
            settings.validate()
        except CloverConfigurationError as error:
            raise InvalidWebhookSignature(str(error)) from error

        signature = headers.get("clover-signature") or headers.get("Clover-Signature") or ""
        verify_webhook_signature(body, signature, settings.webhook_secret)

        import hashlib
        import json

        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("Clover webhook payload must be an object.")
        payment_id = payload.get("id") or payload.get("paymentId")
        event_type = str(payload.get("type") or payload.get("Type") or "").upper()
        payment_status = str(payload.get("status") or payload.get("Status") or "").upper()
        normalized_type = "payment.succeeded" if payment_status == "APPROVED" else (
            "payment.failed" if payment_status in {"FAILED", "DECLINED"} else "payment.updated"
        )
        if event_type and event_type != "PAYMENT":
            normalized_type = f"clover.{event_type.lower()}"
        return [
            NormalizedPaymentEvent(
                type=normalized_type,
                provider=self.key,
                provider_payment_ref=str(payment_id) if payment_id else None,
                raw_event_id=hashlib.sha256(body).hexdigest(),
                payload={"reported_status": payment_status, "event_type": event_type},
            )
        ]

    def refund(
        self,
        session: Session,
        order: Order,
        amount_cents: int | None = None,
    ) -> RefundResult:
        raise PaymentCheckoutError(
            "Clover refunds are not exposed through the M1 payment port yet.",
            code="payment_refund_not_implemented",
        )
