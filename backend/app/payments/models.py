"""Tenant payment configuration and provider-neutral payment event audit."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
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

# Providers with a real adapter. Square stays inert until JDS_SQUARE_* is set.
ENABLED_PROVIDER_KEYS = frozenset({"clover", "square"})
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


class OrganizationOrderSettings(Base):
    """Per-shop ordering options that are not tied to an electronic provider.

    Pay at pickup is OFF unless the shop turns it on. The no-show protections
    (minimum completed orders, maximum order total) always apply when it is on.
    """

    __tablename__ = "organization_order_settings"
    __table_args__ = (
        CheckConstraint(
            "pay_at_pickup_min_completed_orders BETWEEN 0 AND 100",
            name="ck_org_order_settings_min_completed",
        ),
        CheckConstraint(
            "pay_at_pickup_max_total_cents BETWEEN 100 AND 100000",
            name="ck_org_order_settings_max_total",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    pay_at_pickup_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    pay_at_pickup_min_completed_orders: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )
    pay_at_pickup_max_total_cents: Mapped[int] = mapped_column(
        Integer, default=2500, server_default="2500"
    )
    new_order_alert_email: Mapped[str | None] = mapped_column(String(320))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PayAtPickupBlock(Base):
    """A customer who no-showed a pay-at-pickup order at this shop."""

    __tablename__ = "pay_at_pickup_blocks"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "customer_user_id",
            name="uq_pay_at_pickup_blocks_org_customer",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    customer_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("jds_users.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(40), default="no_show", server_default="no_show")
    blocked_at: Mapped[datetime] = mapped_column(
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
