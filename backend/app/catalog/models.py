from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import (
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
    event,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base


class SelectionType(str, Enum):
    SINGLE = "single"
    MULTIPLE = "multiple"


class CatalogModelValidation:
    @validates("slug", "key")
    def validate_identifier(self, attribute: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{attribute} must not be blank.")
        return normalized

    @validates("name")
    def validate_name(self, _: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank.")
        return normalized

    @validates(
        "sort_order",
        "base_price_cents",
        "price_cents",
        "price_adjustment_cents",
        "minimum_selections",
        "maximum_selections",
    )
    def validate_nonnegative_integer(self, attribute: str, value: int) -> int:
        if value < 0:
            raise ValueError(f"{attribute} must be nonnegative.")
        return value


class Category(CatalogModelValidation, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("btrim(slug) <> ''", name="slug_nonblank"),
        CheckConstraint("btrim(name) <> ''", name="name_nonblank"),
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
        UniqueConstraint("organization_id", "slug", name="uq_categories_organization_slug"),
        UniqueConstraint("organization_id", "id", name="uq_categories_organization_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    slug: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    products: Mapped[list[Product]] = relationship(
        back_populates="category",
        foreign_keys="Product.category_id",
        passive_deletes=True,
    )


class Product(CatalogModelValidation, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("btrim(slug) <> ''", name="slug_nonblank"),
        CheckConstraint("btrim(name) <> ''", name="name_nonblank"),
        CheckConstraint("base_price_cents >= 0", name="base_price_nonnegative"),
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
        UniqueConstraint("organization_id", "slug", name="uq_products_organization_slug"),
        UniqueConstraint("organization_id", "id", name="uq_products_organization_id"),
        ForeignKeyConstraint(
            ["organization_id", "category_id"],
            ["categories.organization_id", "categories.id"],
            name="fk_products_organization_category",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_products_single_lunch_special",
            "organization_id",
            unique=True,
            postgresql_where=text("is_lunch_special IS TRUE"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    base_price_cents: Mapped[int] = mapped_column(Integer)
    image_reference: Mapped[str | None] = mapped_column(String(500))
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_lunch_special: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    category: Mapped[Category] = relationship(
        back_populates="products", foreign_keys=[category_id]
    )
    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    modifier_group_assignments: Mapped[list[ProductModifierGroup]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    availability: Mapped[ProductAvailability | None] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    availability_overrides: Mapped[list[ProductAvailabilityOverride]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProductVariant(CatalogModelValidation, Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "key", name="uq_product_variants_product_id_key"),
        CheckConstraint("btrim(key) <> ''", name="key_nonblank"),
        CheckConstraint("btrim(name) <> ''", name="name_nonblank"),
        CheckConstraint("price_cents >= 0", name="price_nonnegative"),
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
    )
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    price_cents: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped[Product] = relationship(back_populates="variants")


class ModifierGroup(CatalogModelValidation, Base):
    __tablename__ = "modifier_groups"
    __table_args__ = (
        CheckConstraint("btrim(key) <> ''", name="key_nonblank"),
        CheckConstraint("btrim(name) <> ''", name="name_nonblank"),
        CheckConstraint(
            "selection_type IN ('single', 'multiple')",
            name="selection_type_valid",
        ),
        CheckConstraint("minimum_selections >= 0", name="minimum_nonnegative"),
        CheckConstraint("maximum_selections >= 0", name="maximum_nonnegative"),
        CheckConstraint(
            "(is_required AND minimum_selections >= 1) "
            "OR (NOT is_required AND minimum_selections = 0)",
            name="required_minimum_consistent",
        ),
        CheckConstraint(
            "(selection_type <> 'single' OR allow_quantity OR maximum_selections = 1) "
            "AND (maximum_selections = 0 OR maximum_selections >= minimum_selections)",
            name="selection_range_valid",
        ),
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
        UniqueConstraint(
            "organization_id", "key", name="uq_modifier_groups_organization_key"
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_modifier_groups_organization_id"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    selection_type: Mapped[SelectionType] = mapped_column(
        String(20),
        default=SelectionType.SINGLE,
        server_default=SelectionType.SINGLE.value,
    )
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    minimum_selections: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    maximum_selections: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    allow_quantity: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    options: Mapped[list[ModifierOption]] = relationship(
        back_populates="modifier_group",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    product_assignments: Mapped[list[ProductModifierGroup]] = relationship(
        back_populates="modifier_group",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @validates("selection_type")
    def validate_selection_type(
        self, _: str, value: SelectionType | str
    ) -> SelectionType:
        try:
            return SelectionType(value)
        except ValueError as error:
            raise ValueError("selection_type must be 'single' or 'multiple'.") from error

    def validate_selection_rules(self) -> None:
        minimum = self.minimum_selections
        maximum = self.maximum_selections

        if self.is_required and minimum < 1:
            raise ValueError("required groups must select at least one option.")
        if not self.is_required and minimum != 0:
            raise ValueError("optional groups must have a minimum of zero.")
        if not self.allow_quantity and self.selection_type == SelectionType.SINGLE and maximum != 1:
            raise ValueError("single-selection groups without quantities must have a maximum of one.")
        if maximum != 0 and maximum < minimum:
            raise ValueError("maximum selections must be zero or at least the minimum.")


class ModifierOption(CatalogModelValidation, Base):
    __tablename__ = "modifier_options"
    __table_args__ = (
        UniqueConstraint(
            "modifier_group_id",
            "key",
            name="uq_modifier_options_modifier_group_id_key",
        ),
        CheckConstraint("btrim(key) <> ''", name="key_nonblank"),
        CheckConstraint("btrim(name) <> ''", name="name_nonblank"),
        CheckConstraint(
            "price_adjustment_cents >= 0",
            name="price_adjustment_nonnegative",
        ),
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    modifier_group_id: Mapped[int] = mapped_column(
        ForeignKey("modifier_groups.id", ondelete="CASCADE"),
        index=True,
    )
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    price_adjustment_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    modifier_group: Mapped[ModifierGroup] = relationship(back_populates="options")


class ProductModifierGroup(CatalogModelValidation, Base):
    __tablename__ = "product_modifier_groups"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    modifier_group_id: Mapped[int] = mapped_column(
        ForeignKey("modifier_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped[Product] = relationship(back_populates="modifier_group_assignments")
    modifier_group: Mapped[ModifierGroup] = relationship(
        back_populates="product_assignments"
    )


@event.listens_for(ModifierGroup, "before_insert")
@event.listens_for(ModifierGroup, "before_update")
def validate_modifier_group_selection_rules(
    _: object, __: object, modifier_group: ModifierGroup
) -> None:
    modifier_group.validate_selection_rules()


# Register relationship targets when catalog models are imported independently.
from app.availability import models as availability_models  # noqa: E402,F401
