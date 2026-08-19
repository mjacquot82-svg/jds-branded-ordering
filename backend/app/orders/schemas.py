from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.customers.schemas import GuestCustomerInput
from app.orders.constants import (
    MAX_LINE_QUANTITY,
    MAX_ORDER_LINES,
    MAX_ORDER_NOTES_LENGTH,
)


class OrderInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModifierSelectionInput(OrderInputSchema):
    modifier_option_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=100)


class ConfiguredOrderLineInput(OrderInputSchema):
    product_id: int = Field(gt=0)
    variant_id: int | None = Field(default=None, gt=0)
    modifier_option_ids: list[int] = Field(default_factory=list, max_length=100)
    modifier_selections: list[ModifierSelectionInput] | None = Field(default=None, max_length=100)
    quantity: int = Field(ge=1, le=MAX_LINE_QUANTITY)

    @field_validator("modifier_option_ids")
    @classmethod
    def validate_unique_modifier_options(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("modifier option IDs must be positive.")
        if len(values) != len(set(values)):
            raise ValueError("modifier option IDs must be unique.")
        return values

    def normalized_modifier_selections(self) -> list[ModifierSelectionInput]:
        if self.modifier_selections is not None:
            return self.modifier_selections
        return [ModifierSelectionInput(modifier_option_id=value, quantity=1) for value in self.modifier_option_ids]


class CreatePendingOrderInput(OrderInputSchema):
    idempotency_key: str = Field(min_length=8, max_length=200)
    customer: GuestCustomerInput
    requested_pickup_at: AwareDatetime
    notes: str | None = Field(default=None, max_length=MAX_ORDER_NOTES_LENGTH)
    lines: list[ConfiguredOrderLineInput] = Field(
        min_length=1,
        max_length=MAX_ORDER_LINES,
    )

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def normalize_idempotency_key(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None
