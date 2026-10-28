"""Smallest safe provider-neutral payment port derived from existing flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.orders.models import Order


@dataclass(frozen=True)
class ReturnUrls:
    success: str
    failure: str
    cancel: str


@dataclass(frozen=True)
class ConnectionStatus:
    connected: bool
    provider: str
    display_hint: str
    environment: str | None = None
    health: str = "disconnected"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckoutSession:
    provider: str
    provider_ref: str
    redirect_url: str | None = None
    client_secret: str | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class PaymentStatusResult:
    status: str  # unpaid|requires_action|pending|paid|failed|cancelled|refunded
    provider: str | None = None
    provider_txn_ref: str | None = None
    amount_cents: int | None = None
    currency: str | None = None
    paid_at: datetime | None = None
    failure_code: str | None = None


@dataclass(frozen=True)
class RefundResult:
    status: str
    provider: str
    provider_refund_ref: str | None = None
    amount_cents: int | None = None


@dataclass(frozen=True)
class NormalizedPaymentEvent:
    type: str
    provider: str
    provider_payment_ref: str | None
    order_public_token: str | None = None
    amount_cents: int | None = None
    raw_event_id: str | None = None
    organization_id: UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class PaymentProvider(Protocol):
    """Adapter contract. New processors implement this; cart/order core stays unchanged."""

    key: str

    def connection_status(
        self, session: Session, organization_id: UUID
    ) -> ConnectionStatus: ...

    def create_checkout(
        self,
        session: Session,
        order: Order,
        *,
        return_urls: ReturnUrls | None = None,
    ) -> CheckoutSession: ...

    def reconcile(self, session: Session, order: Order) -> PaymentStatusResult: ...

    def handle_webhook(
        self,
        session: Session,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> list[NormalizedPaymentEvent]: ...

    def refund(
        self,
        session: Session,
        order: Order,
        amount_cents: int | None = None,
    ) -> RefundResult: ...
