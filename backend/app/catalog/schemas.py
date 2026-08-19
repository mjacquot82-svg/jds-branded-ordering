from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CatalogSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModifierOptionResponse(CatalogSchema):
    id: str
    key: str
    name: str
    price_adjustment_cents: int
    sort_order: int


class ProductModifierGroupResponse(CatalogSchema):
    id: str
    key: str
    name: str
    description: str
    selection_type: Literal["single", "multiple"]
    required: bool
    min_selections: int
    max_selections: int
    allow_quantity: bool
    sort_order: int
    options: list[ModifierOptionResponse]


class ProductVariantResponse(CatalogSchema):
    id: str
    key: str
    name: str
    price_cents: int
    sort_order: int


class ProductResponse(CatalogSchema):
    id: str
    slug: str
    name: str
    description: str
    image: str
    featured: bool
    lunch_special: bool
    base_price_cents: int
    sort_order: int
    variants: list[ProductVariantResponse]
    modifier_groups: list[ProductModifierGroupResponse]


class CategoryResponse(CatalogSchema):
    id: str
    slug: str
    name: str
    note: str
    sort_order: int
    products: list[ProductResponse]


class CatalogPricingResponse(CatalogSchema):
    tax_name: str
    tax_rate_millionths: int = Field(ge=0, le=10_000_000)


class CatalogResponse(CatalogSchema):
    version: str
    generated_at: datetime
    pricing: CatalogPricingResponse
    categories: list[CategoryResponse]


class OwnerCategoryResponse(CatalogSchema):
    id: str
    slug: str
    name: str
    note: str
    published: bool
    sort_order: int


class OwnerModifierGroupResponse(CatalogSchema):
    id: str
    key: str
    name: str
    description: str
    selection_type: Literal["single", "multiple"]
    required: bool
    min_selections: int
    max_selections: int
    allow_quantity: bool
    active: bool
    sort_order: int
    assignment_count: int
    options: list["OwnerModifierOptionResponse"]


class OwnerModifierOptionResponse(CatalogSchema):
    id: str
    key: str
    name: str
    price_adjustment_cents: int
    active: bool
    sort_order: int


class OwnerModifierGroupWrite(CatalogSchema):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    selection_type: Literal["single", "multiple"] = "single"
    required: bool = False
    min_selections: int = Field(default=0, ge=0)
    max_selections: int = Field(default=1, ge=0)
    allow_quantity: bool = False
    active: bool = True
    sort_order: int = Field(default=0, ge=0)


class OwnerModifierOptionWrite(CatalogSchema):
    name: str = Field(min_length=1, max_length=200)
    price_adjustment_cents: int = Field(default=0, ge=0)
    active: bool = True
    sort_order: int = Field(default=0, ge=0)


class OwnerVariantResponse(ProductVariantResponse):
    active: bool


class OwnerProductResponse(CatalogSchema):
    id: str
    slug: str
    name: str
    description: str
    base_price_cents: int
    category_id: str
    image: str
    available: bool
    featured: bool
    lunch_special: bool
    published: bool
    archived: bool
    sort_order: int
    variants: list[OwnerVariantResponse]
    modifier_group_ids: list[str]


class OwnerCatalogResponse(CatalogSchema):
    categories: list[OwnerCategoryResponse]
    modifier_groups: list[OwnerModifierGroupResponse]
    products: list[OwnerProductResponse]


class OwnerVariantWrite(CatalogSchema):
    key: str
    name: str
    price_cents: int = Field(ge=0)
    active: bool = True
    sort_order: int = Field(default=0, ge=0)


class OwnerProductWrite(CatalogSchema):
    slug: str
    name: str
    description: str = ""
    base_price_cents: int = Field(ge=0)
    category_id: int
    image: str = ""
    available: bool = True
    featured: bool = False
    lunch_special: bool = False
    published: bool = True
    sort_order: int = Field(default=0, ge=0)
    variants: list[OwnerVariantWrite] = Field(default_factory=list)
    modifier_group_ids: list[int] = Field(default_factory=list)


class OwnerProductAvailabilityWrite(CatalogSchema):
    available: bool


class LunchSpecialSelectionWrite(CatalogSchema):
    product_id: int | None = Field(default=None, ge=1)
