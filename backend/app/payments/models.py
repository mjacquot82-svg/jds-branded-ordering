"""Tenant payment configuration and provider-neutral payment event audit."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Supported provider keys for M1. Only clover is enabled for real checkout.
ENABLED_PROVIDER_KEYS = frozenset({"clover"})
KNOWN_PROVIDER_KEYS = frozenset({"clover", "stripe", "square", "moneris"})


class OrganizationPaymentSettings(Base):
    """One active electronic payment provider per tenant (M1)."""

    __tablename__ = "organization_payment_settings"
    __table_args__ = (
        Index("ix_org_payment_settings_provider", "provider_key"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    provider_key: Mapped[str] = mapped_column(String(40), nullable=False)
    # Optional encrypted JSON for future API-key providers; Clover keeps tokens
    # in clover_installations. Never returned to the browser.
    encrypted_config: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PaymentEvent(Base):
    """Provider-neutral payment event log (adapters retain provider-specific tables)."""

    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider_key",
            "provider_event_id",
            name="uq_payment_events_org_provider_event",
        ),
        ForeignKeyConstraint(
            ["organization_id", "order_id"],
            ["orders.organization_id", "orders.id"],
            name="fk_payment_events_tenant_order",
            ondelete="RESTRICT",
        ),
        Index("ix_payment_events_organization_created", "organization_id", "created_at"),
        Index("ix_payment_events_organization_checkout", "organization_id", "checkout_ref"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(index=True)
    provider_key: Mapped[str] = mapped_column(String(40), index=True)
    provider_event_id: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(80))
    checkout_ref: Mapped[str | None] = mapped_column(String(200))
    provider_payment_ref: Mapped[str | None] = mapped_column(String(200))
    order_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    outcome: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str | None] = mapped_column(String(200))
    payload_sha256: Mapped[str | None] = mapped_column(String(64))
    # Non-secret provider overflow only; never store raw secrets.
    metadata_json: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def new_payment_event_id() -> UUID:
    return uuid4()
