from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.customers.schemas import GuestCustomerInput
from app.orders.constants import (
    MAX_LINE_QUANTITY,
    MAX_ORDER_LINES,
    MAX_ORDER_NOTES_LENGTH,
    OrderStatus,
)
from app.orders.models import Order, OrderItem, OrderItemModifier
from app.orders.schemas import (
    ConfiguredOrderLineInput,
    CreatePendingOrderInput,
    ModifierSelectionInput,
)


class OrderApiSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrderLineRequest(OrderApiSchema):
    product_id: int = Field(gt=0)
    variant_id: int | None = Field(default=None, gt=0)
    modifier_option_ids: list[int] = Field(default_factory=list, max_length=100)
    modifier_selections: list[ModifierSelectionInput] | None = Field(default=None, max_length=100)
    quantity: int = Field(ge=1, le=MAX_LINE_QUANTITY)

    @field_validator("modifier_option_ids")
    @classmethod
    def validate_modifier_option_ids(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("modifier option IDs must be positive.")
        if len(values) != len(set(values)):
            raise ValueError("modifier option IDs must be unique.")
        return values

    def to_domain(self) -> ConfiguredOrderLineInput:
        return ConfiguredOrderLineInput(**self.model_dump())


class CreateOrderRequest(OrderApiSchema):
    idempotency_key: str = Field(min_length=8, max_length=200)
    customer: GuestCustomerInput
    requested_pickup_at: datetime
    notes: str | None = Field(default=None, max_length=MAX_ORDER_NOTES_LENGTH)
    lines: list[OrderLineRequest] = Field(
        min_length=1,
        max_length=MAX_ORDER_LINES,
    )

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def normalize_idempotency_key(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("requested_pickup_at")
    @classmethod
    def validate_aware_pickup(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requested_pickup_at must include timezone information.")
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    def to_domain(self) -> CreatePendingOrderInput:
        return CreatePendingOrderInput(
            idempotency_key=self.idempotency_key,
            customer=self.customer,
            requested_pickup_at=self.requested_pickup_at,
            notes=self.notes,
            lines=[line.to_domain() for line in self.lines],
        )


class GuestCustomerSnapshot(OrderApiSchema):
    name: str
    email: str
    phone: str


class OrderModifierSnapshot(OrderApiSchema):
    group_key: str
    group_name: str
    option_key: str
    option_name: str
    price_adjustment_cents: int
    quantity: int

    @classmethod
    def from_model(
        cls,
        modifier: OrderItemModifier,
    ) -> "OrderModifierSnapshot":
        return cls(
            group_key=modifier.modifier_group_key,
            group_name=modifier.modifier_group_name,
            option_key=modifier.modifier_option_key,
            option_name=modifier.modifier_option_name,
            price_adjustment_cents=modifier.price_adjustment_cents,
            quantity=modifier.quantity,
        )


class OrderItemSnapshot(OrderApiSchema):
    product_slug: str
    product_name: str
    variant_key: str | None
    variant_name: str | None
    base_unit_price_cents: int
    unit_price_cents: int
    quantity: int
    line_subtotal_cents: int
    modifiers: list[OrderModifierSnapshot]

    @classmethod
    def from_model(cls, item: OrderItem) -> "OrderItemSnapshot":
        return cls(
            product_slug=item.product_slug,
            product_name=item.product_name,
            variant_key=item.variant_key,
            variant_name=item.variant_name,
            base_unit_price_cents=item.base_unit_price_cents,
            unit_price_cents=item.unit_price_cents,
            quantity=item.quantity,
            line_subtotal_cents=item.line_subtotal_cents,
            modifiers=[
                OrderModifierSnapshot.from_model(modifier)
                for modifier in item.modifiers
            ],
        )


class PendingOrderResponse(OrderApiSchema):
    public_token: str
    status: OrderStatus
    customer: GuestCustomerSnapshot
    notes: str | None
    requested_pickup_at: datetime
    business_timezone: str
    currency: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemSnapshot]

    @classmethod
    def from_model(cls, order: Order) -> "PendingOrderResponse":
        return cls(
            public_token=order.public_access_token,
            status=order.status,
            customer=GuestCustomerSnapshot(
                name=order.guest_name,
                email=order.guest_email,
                phone=order.guest_phone,
            ),
            notes=order.notes,
            requested_pickup_at=order.requested_pickup_at.astimezone(timezone.utc),
            business_timezone=order.business_timezone,
            currency=order.currency,
            subtotal_cents=order.subtotal_cents,
            tax_cents=order.tax_cents,
            total_cents=order.total_cents,
            expires_at=order.expires_at.astimezone(timezone.utc),
            created_at=order.created_at.astimezone(timezone.utc),
            updated_at=order.updated_at.astimezone(timezone.utc),
            items=[OrderItemSnapshot.from_model(item) for item in order.items],
        )


class OrderErrorDetail(OrderApiSchema):
    code: str
    message: str


class OrderErrorResponse(OrderApiSchema):
    detail: OrderErrorDetail
