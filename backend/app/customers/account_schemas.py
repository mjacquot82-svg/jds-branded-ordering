from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.customers.schemas import normalize_phone_to_e164


class CustomerSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerProfileResponse(CustomerSchema):
    name: str
    email: str
    phone: str
    preferred_pickup_minutes: int | None
    preferred_pickup_notes: str


class CustomerProfileUpdate(CustomerSchema):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=7, max_length=30)
    preferred_pickup_minutes: int | None = Field(default=None, ge=0, le=1440)
    preferred_pickup_notes: str = Field(default="", max_length=500)

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, value: object) -> object:
        return normalize_phone_to_e164(value)


class CustomerOrderSummaryModifier(CustomerSchema):
    group_name: str
    option_name: str
    quantity: int


class CustomerOrderSummaryItem(CustomerSchema):
    product_name: str
    variant_name: str | None
    quantity: int
    modifiers: list[CustomerOrderSummaryModifier]


class CustomerOrderSummary(CustomerSchema):
    id: int
    status: str
    requested_pickup_at: str
    total_cents: int
    created_at: str
    item_count: int
    fulfillment_status: str
    business_timezone: str
    first_item: CustomerOrderSummaryItem


class CustomerQuickOrderModifier(CustomerSchema):
    option_id: str
    option_name: str
    quantity: int


class CustomerQuickOrderConfiguration(CustomerSchema):
    product_id: str
    variant_id: str | None
    modifiers: list[CustomerQuickOrderModifier]
    unit_price_cents: int


class CustomerQuickOrderResponse(CustomerSchema):
    product_ids: list[str]
    configurations: list[CustomerQuickOrderConfiguration] = Field(default_factory=list)
