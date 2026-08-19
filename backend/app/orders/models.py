from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.orders.constants import FulfillmentStatus, MAX_LINE_QUANTITY, OrderStatus


class OrderModelValidation:
    @validates(
        "guest_name",
        "guest_email",
        "guest_phone",
        "business_timezone",
        "tax_name",
        "product_name",
        "product_slug",
        "modifier_group_key",
        "modifier_group_name",
        "modifier_option_key",
        "modifier_option_name",
        "idempotency_key",
        "request_fingerprint",
        "public_access_token",
    )
    def validate_nonblank(self, attribute: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{attribute} must not be blank.")
        return normalized

    @validates(
        "subtotal_cents",
        "tax_cents",
        "total_cents",
        "base_unit_price_cents",
        "unit_price_cents",
        "line_subtotal_cents",
        "price_adjustment_cents",
        "sort_order",
        "tax_rate_millionths",
    )
    def validate_nonnegative(self, attribute: str, value: int) -> int:
        if value < 0:
            raise ValueError(f"{attribute} must be nonnegative.")
        return value


class Order(OrderModelValidation, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'payment_pending', 'paid', 'payment_failed')",
            name="status_valid",
        ),
        Index(
            "ix_orders_organization_active_queue",
            "organization_id",
            "status",
            "fulfillment_status",
            "requested_pickup_at",
            "created_at",
        ),
        Index(
            "ix_orders_organization_customer_created",
            "organization_id",
            "customer_user_id",
            "created_at",
        ),
        Index(
            "ix_orders_organization_fulfillment_pickup",
            "organization_id",
            "fulfillment_status",
            "requested_pickup_at",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_orders_organization_id_id"
        ),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_orders_organization_idempotency_key",
        ),
        UniqueConstraint(
            "organization_id",
            "public_access_token",
            name="uq_orders_organization_public_access_token",
        ),
        CheckConstraint(
            "fulfillment_status IN "
            "('new', 'preparing', 'ready', 'completed', 'cancelled')",
            name="fulfillment_status_valid",
        ),
        CheckConstraint("btrim(idempotency_key) <> ''", name="idempotency_nonblank"),
        CheckConstraint(
            "char_length(request_fingerprint) = 64",
            name="request_fingerprint_nonblank",
        ),
        CheckConstraint(
            "btrim(public_access_token) <> ''",
            name="public_access_token_nonblank",
        ),
        CheckConstraint("btrim(guest_name) <> ''", name="guest_name_nonblank"),
        CheckConstraint("btrim(guest_email) <> ''", name="guest_email_nonblank"),
        CheckConstraint("btrim(guest_phone) <> ''", name="guest_phone_nonblank"),
        CheckConstraint(
            "btrim(business_timezone) <> ''",
            name="business_timezone_nonblank",
        ),
        CheckConstraint(
            "notes IS NULL OR (btrim(notes) <> '' AND char_length(notes) <= 2000)",
            name="notes_valid",
        ),
        CheckConstraint(
            "currency = upper(currency) AND char_length(currency) = 3",
            name="currency_valid",
        ),
        CheckConstraint("subtotal_cents >= 0", name="subtotal_nonnegative"),
        CheckConstraint("tax_cents >= 0", name="tax_nonnegative"),
        CheckConstraint("btrim(tax_name) <> ''", name="tax_name_nonblank"),
        CheckConstraint(
            "tax_rate_millionths BETWEEN 0 AND 10000000",
            name="tax_rate_millionths_valid",
        ),
        CheckConstraint("total_cents >= 0", name="total_nonnegative"),
        CheckConstraint(
            "total_cents = subtotal_cents + tax_cents",
            name="total_consistent",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        CheckConstraint(
            "(clover_installation_id IS NULL AND "
            "clover_environment IS NULL AND "
            "clover_merchant_id IS NULL AND "
            "clover_checkout_session_id IS NULL AND "
            "clover_checkout_url IS NULL AND "
            "clover_checkout_expires_at IS NULL) OR "
            "(clover_installation_id IS NOT NULL AND "
            "clover_environment IS NOT NULL AND "
            "clover_merchant_id IS NOT NULL AND "
            "clover_checkout_session_id IS NOT NULL AND "
            "clover_checkout_url IS NOT NULL AND "
            "clover_checkout_expires_at IS NOT NULL)",
            name="clover_checkout_consistent",
        ),
        ForeignKeyConstraint(
            [
                "organization_id", "clover_installation_id",
                "clover_environment", "clover_merchant_id",
            ],
            [
                "clover_installations.organization_id", "clover_installations.id",
                "clover_installations.environment", "clover_installations.merchant_id",
            ],
            name="fk_orders_tenant_clover_installation", ondelete="RESTRICT",
        ),
        Index("ix_orders_organization_clover_checkout", "organization_id", "clover_checkout_session_id"),
        UniqueConstraint(
            "organization_id", "clover_checkout_session_id",
            name="uq_orders_organization_clover_checkout_session",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    customer_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jds_users.id", ondelete="SET NULL"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    public_access_token: Mapped[str] = mapped_column(String(200))
    status: Mapped[OrderStatus] = mapped_column(
        String(30),
        default=OrderStatus.PENDING,
        server_default=OrderStatus.PENDING.value,
    )
    fulfillment_status: Mapped[FulfillmentStatus] = mapped_column(
        String(30),
        default=FulfillmentStatus.NEW,
        server_default=FulfillmentStatus.NEW.value,
    )
    guest_name: Mapped[str] = mapped_column(String(200))
    guest_email: Mapped[str] = mapped_column(String(320))
    guest_phone: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(Text)
    requested_pickup_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    business_timezone: Mapped[str] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(
        String(3),
        default="CAD",
        server_default="CAD",
    )
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tax_name: Mapped[str] = mapped_column(
        String(50), default="HST", server_default="HST"
    )
    tax_rate_millionths: Mapped[int] = mapped_column(
        Integer, default=1_300_000, server_default="1300000"
    )
    total_cents: Mapped[int] = mapped_column(Integer)
    clover_installation_id: Mapped[UUID | None] = mapped_column(index=True)
    clover_environment: Mapped[str | None] = mapped_column(String(20))
    clover_merchant_id: Mapped[str | None] = mapped_column(String(100))
    clover_checkout_session_id: Mapped[str | None] = mapped_column(
        String(200)
    )
    clover_checkout_url: Mapped[str | None] = mapped_column(Text)
    clover_checkout_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    fulfillment_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    preparing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="OrderItem.sort_order",
    )

    @validates("status")
    def validate_status(self, _: str, value: OrderStatus | str) -> OrderStatus:
        try:
            return OrderStatus(value)
        except ValueError as error:
            raise ValueError("status is invalid.") from error

    @validates("fulfillment_status")
    def validate_fulfillment_status(
        self, _: str, value: FulfillmentStatus | str
    ) -> FulfillmentStatus:
        try:
            return FulfillmentStatus(value)
        except ValueError as error:
            raise ValueError("fulfillment_status is invalid.") from error

    @validates("notes")
    def validate_notes(self, _: str, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("notes must not be blank.")
        if len(normalized) > 2000:
            raise ValueError("notes must not exceed 2000 characters.")
        return normalized


class OrderItem(OrderModelValidation, Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("btrim(product_name) <> ''", name="product_name_nonblank"),
        CheckConstraint("btrim(product_slug) <> ''", name="product_slug_nonblank"),
        CheckConstraint(
            "variant_name IS NULL OR btrim(variant_name) <> ''",
            name="variant_name_nonblank",
        ),
        CheckConstraint(
            "variant_key IS NULL OR btrim(variant_key) <> ''",
            name="variant_key_nonblank",
        ),
        CheckConstraint(
            "(source_variant_id IS NULL AND variant_name IS NULL "
            "AND variant_key IS NULL) OR "
            "(variant_name IS NOT NULL AND variant_key IS NOT NULL)",
            name="variant_snapshot_consistent",
        ),
        CheckConstraint(
            f"quantity BETWEEN 1 AND {MAX_LINE_QUANTITY}",
            name="quantity_valid",
        ),
        CheckConstraint(
            "base_unit_price_cents >= 0",
            name="base_unit_price_nonnegative",
        ),
        CheckConstraint("unit_price_cents >= 0", name="unit_price_nonnegative"),
        CheckConstraint(
            "line_subtotal_cents = unit_price_cents * quantity",
            name="line_subtotal_consistent",
        ),
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
        UniqueConstraint("order_id", "sort_order", name="uq_order_items_order_sort"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        index=True,
    )
    source_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        index=True,
    )
    source_variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        index=True,
    )
    product_slug: Mapped[str] = mapped_column(String(100))
    product_name: Mapped[str] = mapped_column(String(200))
    variant_key: Mapped[str | None] = mapped_column(String(100))
    variant_name: Mapped[str | None] = mapped_column(String(200))
    base_unit_price_cents: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    line_subtotal_cents: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    order: Mapped[Order] = relationship(back_populates="items")
    modifiers: Mapped[list[OrderItemModifier]] = relationship(
        back_populates="order_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="OrderItemModifier.sort_order",
    )

    @validates("quantity")
    def validate_quantity(self, _: str, value: int) -> int:
        if not 1 <= value <= MAX_LINE_QUANTITY:
            raise ValueError(
                f"quantity must be between 1 and {MAX_LINE_QUANTITY}."
            )
        return value

    @validates("variant_key", "variant_name")
    def validate_optional_snapshot(
        self,
        attribute: str,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{attribute} must not be blank.")
        return normalized


class OrderItemModifier(OrderModelValidation, Base):
    __tablename__ = "order_item_modifiers"
    __table_args__ = (
        CheckConstraint(
            "btrim(modifier_group_key) <> ''",
            name="group_key_nonblank",
        ),
        CheckConstraint(
            "btrim(modifier_group_name) <> ''",
            name="group_name_nonblank",
        ),
        CheckConstraint(
            "btrim(modifier_option_key) <> ''",
            name="option_key_nonblank",
        ),
        CheckConstraint(
            "btrim(modifier_option_name) <> ''",
            name="option_name_nonblank",
        ),
        CheckConstraint(
            "price_adjustment_cents >= 0",
            name="price_adjustment_nonnegative",
        ),
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
        CheckConstraint("quantity >= 1", name="quantity_positive"),
        UniqueConstraint(
            "order_item_id",
            "sort_order",
            name="uq_order_item_modifiers_item_sort",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"),
        index=True,
    )
    source_modifier_group_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "modifier_groups.id",
            name="fk_order_item_modifiers_source_group",
            ondelete="SET NULL",
        ),
        index=True,
    )
    source_modifier_option_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "modifier_options.id",
            name="fk_order_item_modifiers_source_option",
            ondelete="SET NULL",
        ),
        index=True,
    )
    modifier_group_key: Mapped[str] = mapped_column(String(100))
    modifier_group_name: Mapped[str] = mapped_column(String(200))
    modifier_option_key: Mapped[str] = mapped_column(String(100))
    modifier_option_name: Mapped[str] = mapped_column(String(200))
    price_adjustment_cents: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    order_item: Mapped[OrderItem] = relationship(back_populates="modifiers")
