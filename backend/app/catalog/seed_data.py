from collections.abc import Iterable
from dataclasses import dataclass

from app.catalog.models import SelectionType


@dataclass(frozen=True)
class CategorySeed:
    slug: str
    name: str
    description: str


@dataclass(frozen=True)
class VariantSeed:
    key: str
    name: str
    price_cents: int


@dataclass(frozen=True)
class ProductSeed:
    slug: str
    category_slug: str
    name: str
    description: str
    base_price_cents: int
    image_reference: str
    is_featured: bool
    variants: tuple[VariantSeed, ...] = ()
    modifier_group_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModifierOptionSeed:
    key: str
    name: str
    price_adjustment_cents: int


@dataclass(frozen=True)
class ModifierGroupSeed:
    key: str
    name: str
    selection_type: SelectionType
    is_required: bool
    minimum_selections: int
    maximum_selections: int
    options: tuple[ModifierOptionSeed, ...]


@dataclass(frozen=True)
class CatalogSeed:
    categories: tuple[CategorySeed, ...]
    products: tuple[ProductSeed, ...]
    modifier_groups: tuple[ModifierGroupSeed, ...]


SIZE_PRICE_ADJUSTMENTS = (
    ("small", "Small", 0),
    ("medium", "Medium", 75),
    ("large", "Large", 125),
)


def size_variants(base_price_cents: int) -> tuple[VariantSeed, ...]:
    return tuple(
        VariantSeed(
            key=key,
            name=name,
            price_cents=base_price_cents + adjustment,
        )
        for key, name, adjustment in SIZE_PRICE_ADJUSTMENTS
    )


GUEST_HOUSE_CATALOG = CatalogSeed(
    categories=(
        CategorySeed("coffee", "Coffee", "House cups for slow mornings."),
        CategorySeed(
            "espresso",
            "Espresso",
            "Steamed milk, soft foam, and signature favorites.",
        ),
        CategorySeed(
            "tea",
            "Tea",
            "Gentle cups for slow reading and quiet afternoons.",
        ),
        CategorySeed(
            "iced-drinks",
            "Iced Drinks",
            "Cool café pours for warm afternoons.",
        ),
        CategorySeed(
            "smoothies",
            "Smoothies",
            "Bright blends from the cold bar.",
        ),
        CategorySeed(
            "breakfast",
            "Breakfast",
            "Simple starts and fresh morning plates.",
        ),
        CategorySeed(
            "pastries",
            "Pastries",
            "Bakery case comforts, warmed on request.",
        ),
        CategorySeed("snacks", "Snacks", "Small bites for an easy pause."),
        CategorySeed(
            "extras",
            "Extras",
            "Little add-ons for drinks and bakery picks.",
        ),
    ),
    products=(
        ProductSeed(
            slug="drip-coffee",
            category_slug="coffee",
            name="Drip Coffee",
            description="Warm, steady, and ready from the counter.",
            base_price_cents=375,
            image_reference="coffee",
            is_featured=True,
            variants=size_variants(375),
            modifier_group_keys=("milk",),
        ),
        ProductSeed(
            slug="cold-brew",
            category_slug="iced-drinks",
            name="Cold Brew",
            description="Slow-steeped and poured over ice.",
            base_price_cents=475,
            image_reference="coffee",
            is_featured=True,
            variants=size_variants(475),
            modifier_group_keys=("milk", "flavour-shots"),
        ),
        ProductSeed(
            slug="latte",
            category_slug="espresso",
            name="Latte",
            description="Velvety milk and a double shot.",
            base_price_cents=525,
            image_reference="coffee",
            is_featured=True,
            variants=size_variants(525),
            modifier_group_keys=("milk", "flavour-shots"),
        ),
        ProductSeed(
            slug="cappuccino",
            category_slug="espresso",
            name="Cappuccino",
            description="Foamy, cozy, and balanced.",
            base_price_cents=525,
            image_reference="coffee",
            is_featured=False,
            variants=size_variants(525),
            modifier_group_keys=("milk",),
        ),
        ProductSeed(
            slug="chai-latte",
            category_slug="tea",
            name="Chai Latte",
            description="Spiced tea with steamed milk.",
            base_price_cents=525,
            image_reference="coffee",
            is_featured=False,
            variants=size_variants(525),
            modifier_group_keys=("milk",),
        ),
        ProductSeed(
            slug="berry-smoothie",
            category_slug="smoothies",
            name="Berry Smoothie",
            description="Mixed berries, banana, and yogurt.",
            base_price_cents=650,
            image_reference="water",
            is_featured=False,
            variants=size_variants(650),
        ),
        ProductSeed(
            slug="granola-yogurt",
            category_slug="breakfast",
            name="Granola Yogurt",
            description="Honey, yogurt, and a crunchy top.",
            base_price_cents=550,
            image_reference="pastry",
            is_featured=False,
        ),
        ProductSeed(
            slug="croissant",
            category_slug="pastries",
            name="Butter Croissant",
            description="Flaky, simple, and warmed on request.",
            base_price_cents=450,
            image_reference="pastry",
            is_featured=True,
            modifier_group_keys=("toast",),
        ),
        ProductSeed(
            slug="blueberry-muffin",
            category_slug="pastries",
            name="Blueberry Muffin",
            description="Bakery-style with a tender crumb.",
            base_price_cents=395,
            image_reference="pastry",
            is_featured=False,
        ),
        ProductSeed(
            slug="trail-mix",
            category_slug="snacks",
            name="Trail Mix",
            description="A small jar with nuts, seeds, and dried fruit.",
            base_price_cents=375,
            image_reference="pastry",
            is_featured=False,
        ),
        ProductSeed(
            slug="vanilla-shot",
            category_slug="extras",
            name="Vanilla Shot",
            description="Soft and familiar.",
            base_price_cents=75,
            image_reference="coffee",
            is_featured=False,
        ),
    ),
    modifier_groups=(
        ModifierGroupSeed(
            key="milk",
            name="Milk",
            selection_type=SelectionType.SINGLE,
            is_required=False,
            minimum_selections=0,
            maximum_selections=1,
            options=(
                ModifierOptionSeed("whole", "Whole milk", 0),
                ModifierOptionSeed("oat", "Oat", 85),
                ModifierOptionSeed("almond", "Almond", 85),
                ModifierOptionSeed("soy", "Soy", 85),
                ModifierOptionSeed("coconut", "Coconut", 85),
            ),
        ),
        ModifierGroupSeed(
            key="flavour-shots",
            name="Flavour shots",
            selection_type=SelectionType.MULTIPLE,
            is_required=False,
            minimum_selections=0,
            maximum_selections=0,
            options=(
                ModifierOptionSeed("vanilla", "Vanilla", 75),
                ModifierOptionSeed("caramel", "Caramel", 75),
                ModifierOptionSeed("hazelnut", "Hazelnut", 75),
            ),
        ),
        ModifierGroupSeed(
            key="toast",
            name="Toast",
            selection_type=SelectionType.SINGLE,
            is_required=False,
            minimum_selections=0,
            maximum_selections=1,
            options=(
                ModifierOptionSeed("plain", "Plain", 0),
                ModifierOptionSeed("butter", "Butter", 35),
                ModifierOptionSeed("jam", "House jam", 65),
            ),
        ),
    ),
)


def validate_catalog_seed(catalog: CatalogSeed) -> None:
    category_slugs = _unique_nonblank(
        (category.slug for category in catalog.categories),
        "category slug",
    )
    modifier_group_keys = _unique_nonblank(
        (group.key for group in catalog.modifier_groups),
        "modifier group key",
    )
    _unique_nonblank((product.slug for product in catalog.products), "product slug")

    for position, category in enumerate(catalog.categories):
        _require_nonblank(category.name, f"category {category.slug} name")
        _require_nonnegative(position, f"category {category.slug} sort order")

    for product in catalog.products:
        _require_nonblank(product.name, f"product {product.slug} name")
        _require_nonnegative(
            product.base_price_cents,
            f"product {product.slug} base price",
        )
        if product.category_slug not in category_slugs:
            raise ValueError(
                f"product {product.slug} references unknown category "
                f"{product.category_slug}."
            )

        _unique_nonblank(
            (variant.key for variant in product.variants),
            f"variant key for product {product.slug}",
        )
        for variant in product.variants:
            _require_nonblank(
                variant.name,
                f"variant {product.slug}/{variant.key} name",
            )
            _require_nonnegative(
                variant.price_cents,
                f"variant {product.slug}/{variant.key} price",
            )

        if len(set(product.modifier_group_keys)) != len(
            product.modifier_group_keys
        ):
            raise ValueError(
                f"product {product.slug} has duplicate modifier group assignments."
            )
        unknown_groups = set(product.modifier_group_keys) - modifier_group_keys
        if unknown_groups:
            raise ValueError(
                f"product {product.slug} references unknown modifier groups: "
                f"{sorted(unknown_groups)}."
            )

    for group in catalog.modifier_groups:
        _require_nonblank(group.name, f"modifier group {group.key} name")
        _require_nonnegative(
            group.minimum_selections,
            f"modifier group {group.key} minimum",
        )
        _require_nonnegative(
            group.maximum_selections,
            f"modifier group {group.key} maximum",
        )
        if group.is_required != (group.minimum_selections >= 1):
            raise ValueError(
                f"modifier group {group.key} has inconsistent required/minimum values."
            )
        if (
            group.selection_type == SelectionType.SINGLE
            and group.maximum_selections != 1
        ):
            raise ValueError(
                f"single modifier group {group.key} must have maximum one."
            )
        if (
            group.selection_type == SelectionType.MULTIPLE
            and group.maximum_selections != 0
            and group.maximum_selections < group.minimum_selections
        ):
            raise ValueError(
                f"modifier group {group.key} maximum must be unlimited or "
                "at least its minimum."
            )

        _unique_nonblank(
            (option.key for option in group.options),
            f"option key for modifier group {group.key}",
        )
        for option in group.options:
            _require_nonblank(
                option.name,
                f"modifier option {group.key}/{option.key} name",
            )
            _require_nonnegative(
                option.price_adjustment_cents,
                f"modifier option {group.key}/{option.key} price adjustment",
            )


def _unique_nonblank(values: Iterable[str], label: str) -> set[str]:
    normalized_values: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must not be blank.")
        normalized_values.append(value)

    if len(set(normalized_values)) != len(normalized_values):
        raise ValueError(f"{label} values must be unique.")
    return set(normalized_values)


def _require_nonblank(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must not be blank.")


def _require_nonnegative(value: int, label: str) -> None:
    if value < 0:
        raise ValueError(f"{label} must be nonnegative.")
