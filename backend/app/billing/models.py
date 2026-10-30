"""Tables for JDS platform billing and per-shop usage counters."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ACCOUNT_STATUSES = ("none", "active", "past_due", "paused", "cancelled")


class ShopBillingAccount(Base):
    """One per shop: the card on file and the Square subscription billed to JDS's own Square account."""

    __tablename__ = "shop_billing_accounts"
    __table_args__ = (
        CheckConstraint("status IN ('none','active','past_due','paused','cancelled')", name="ck_shop_billing_accounts_status"),
        CheckConstraint("extra_locations >= 0", name="ck_shop_billing_accounts_extra_locations"),
        CheckConstraint("package_key IS NULL OR package_key IN ('starter','plus','pro')", name="ck_shop_billing_accounts_package"),
        CheckConstraint("pending_package_key IS NULL OR pending_package_key IN ('starter','plus','pro')", name="ck_shop_billing_accounts_pending_package"),
    )
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="none", server_default="none")
    package_key: Mapped[str | None] = mapped_column(String(20))
    pending_package_key: Mapped[str | None] = mapped_column(String(20))
    extra_locations: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    monthly_amount_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), default="CAD", server_default="CAD")
    square_customer_id: Mapped[str | None] = mapped_column(String(200), index=True)
    square_card_id: Mapped[str | None] = mapped_column(String(200))
    square_subscription_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    card_brand: Mapped[str | None] = mapped_column(String(40))
    card_last4: Mapped[str | None] = mapped_column(String(4))
    card_exp_month: Mapped[int | None] = mapped_column(Integer)
    card_exp_year: Mapped[int | None] = mapped_column(Integer)
    next_bill_on: Mapped[date | None] = mapped_column(Date)
    past_due_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grace_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BillingPayment(Base):
    """A paid or failed platform charge, one row per Square webhook event (idempotent)."""

    __tablename__ = "billing_payments"
    __table_args__ = (CheckConstraint("outcome IN ('paid','failed')", name="ck_billing_payments_outcome"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    provider_event_id: Mapped[str] = mapped_column(String(200), unique=True)
    provider_invoice_id: Mapped[str | None] = mapped_column(String(200))
    outcome: Mapped[str] = mapped_column(String(10))
    amount_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), default="CAD", server_default="CAD")
    package_key: Mapped[str | None] = mapped_column(String(20))
    period: Mapped[str] = mapped_column(String(7), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShopUsageCounter(Base):
    """Cheap per-shop, per-month counters (emails sent, texts sent, ...) for cost splitting."""

    __tablename__ = "shop_usage_counters"
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    period: Mapped[str] = mapped_column(String(7), primary_key=True)
    metric: Mapped[str] = mapped_column(String(40), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
