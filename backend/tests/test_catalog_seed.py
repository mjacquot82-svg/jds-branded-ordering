from collections.abc import Iterator
from dataclasses import replace

import pytest
from alembic import command
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import app.catalog.seed as seed_module
from app.catalog.models import (
    Category,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductModifierGroup,
    ProductVariant,
)
from app.catalog.seed import seed_catalog
from app.catalog.seed_data import GUEST_HOUSE_CATALOG
from app.tenancy.resolver import LADELS_ORGANIZATION_ID
from tests.test_migrations import make_alembic_config


@pytest.fixture
def seed_engine(postgresql_url: str) -> Iterator[Engine]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE product_modifier_groups, modifier_options, "
                "product_variants, products, modifier_groups, categories "
                "RESTART IDENTITY CASCADE"
            )
        )

    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE product_modifier_groups, modifier_options, "
                    "product_variants, products, modifier_groups, categories "
                    "RESTART IDENTITY CASCADE"
                )
            )
        engine.dispose()


def table_counts(session: Session) -> tuple[int, ...]:
    return (
        session.scalar(select(func.count()).select_from(Category)),
        session.scalar(select(func.count()).select_from(Product)),
        session.scalar(select(func.count()).select_from(ProductVariant)),
        session.scalar(select(func.count()).select_from(ModifierGroup)),
        session.scalar(select(func.count()).select_from(ModifierOption)),
        session.scalar(select(func.count()).select_from(ProductModifierGroup)),
    )


@pytest.mark.postgresql
def test_seed_succeeds_on_empty_database_and_matches_frontend_catalog(
    seed_engine: Engine,
) -> None:
    with Session(seed_engine) as session:
        seed_catalog(session)

        categories = session.scalars(
            select(Category).order_by(Category.sort_order)
        ).all()
        products = session.scalars(select(Product).order_by(Product.sort_order)).all()
        groups = session.scalars(
            select(ModifierGroup).order_by(ModifierGroup.sort_order)
        ).all()

        assert table_counts(session) == (9, 11, 18, 3, 11, 8)
        assert [
            (category.slug, category.name, category.description)
            for category in categories
        ] == [
            ("coffee", "Coffee", "House cups for slow mornings."),
            (
                "espresso",
                "Espresso",
                "Steamed milk, soft foam, and signature favorites.",
            ),
            (
                "tea",
                "Tea",
                "Gentle cups for slow reading and quiet afternoons.",
            ),
            (
                "iced-drinks",
                "Iced Drinks",
                "Cool café pours for warm afternoons.",
            ),
            ("smoothies", "Smoothies", "Bright blends from the cold bar."),
            (
                "breakfast",
                "Breakfast",
                "Simple starts and fresh morning plates.",
            ),
            (
                "pastries",
                "Pastries",
                "Bakery case comforts, warmed on request.",
            ),
            ("snacks", "Snacks", "Small bites for an easy pause."),
            (
                "extras",
                "Extras",
                "Little add-ons for drinks and bakery picks.",
            ),
        ]
        assert all(category.is_published for category in categories)

        assert [
            (
                product.slug,
                product.name,
                product.description,
                product.base_price_cents,
                product.category.slug,
                product.image_reference,
                product.is_featured,
            )
            for product in products
        ] == [
            (
                "drip-coffee",
                "Drip Coffee",
                "Warm, steady, and ready from the counter.",
                375,
                "coffee",
                "coffee",
                True,
            ),
            (
                "cold-brew",
                "Cold Brew",
                "Slow-steeped and poured over ice.",
                475,
                "iced-drinks",
                "coffee",
                True,
            ),
            (
                "latte",
                "Latte",
                "Velvety milk and a double shot.",
                525,
                "espresso",
                "coffee",
                True,
            ),
            (
                "cappuccino",
                "Cappuccino",
                "Foamy, cozy, and balanced.",
                525,
                "espresso",
                "coffee",
                False,
            ),
            (
                "chai-latte",
                "Chai Latte",
                "Spiced tea with steamed milk.",
                525,
                "tea",
                "coffee",
                False,
            ),
            (
                "berry-smoothie",
                "Berry Smoothie",
                "Mixed berries, banana, and yogurt.",
                650,
                "smoothies",
                "water",
                False,
            ),
            (
                "granola-yogurt",
                "Granola Yogurt",
                "Honey, yogurt, and a crunchy top.",
                550,
                "breakfast",
                "pastry",
                False,
            ),
            (
                "croissant",
                "Butter Croissant",
                "Flaky, simple, and warmed on request.",
                450,
                "pastries",
                "pastry",
                True,
            ),
            (
                "blueberry-muffin",
                "Blueberry Muffin",
                "Bakery-style with a tender crumb.",
                395,
                "pastries",
                "pastry",
                False,
            ),
            (
                "trail-mix",
                "Trail Mix",
                "A small jar with nuts, seeds, and dried fruit.",
                375,
                "snacks",
                "pastry",
                False,
            ),
            (
                "vanilla-shot",
                "Vanilla Shot",
                "Soft and familiar.",
                75,
                "extras",
                "coffee",
                False,
            ),
        ]
        assert all(product.is_published for product in products)
        assert all(product.archived_at is None for product in products)

        variants = session.execute(
            select(
                Product.slug,
                ProductVariant.key,
                ProductVariant.name,
                ProductVariant.price_cents,
            )
            .join(ProductVariant.product)
            .order_by(Product.sort_order, ProductVariant.sort_order)
        ).all()
        expected_variant_prices = {
            "drip-coffee": (375, 450, 500),
            "cold-brew": (475, 550, 600),
            "latte": (525, 600, 650),
            "cappuccino": (525, 600, 650),
            "chai-latte": (525, 600, 650),
            "berry-smoothie": (650, 725, 775),
        }
        assert variants == [
            (product_slug, key, name, price)
            for product_slug, prices in expected_variant_prices.items()
            for (key, name), price in zip(
                (("small", "Small"), ("medium", "Medium"), ("large", "Large")),
                prices,
                strict=True,
            )
        ]

        assert [
            (
                group.key,
                group.name,
                group.selection_type,
                group.is_required,
                group.minimum_selections,
                group.maximum_selections,
            )
            for group in groups
        ] == [
            ("milk", "Milk", "single", False, 0, 1),
            ("flavour-shots", "Flavour shots", "multiple", False, 0, 0),
            ("toast", "Toast", "single", False, 0, 1),
        ]

        options = session.execute(
            select(
                ModifierGroup.key,
                ModifierOption.key,
                ModifierOption.name,
                ModifierOption.price_adjustment_cents,
            )
            .join(ModifierOption.modifier_group)
            .order_by(ModifierGroup.sort_order, ModifierOption.sort_order)
        ).all()
        assert options == [
            ("milk", "whole", "Whole milk", 0),
            ("milk", "oat", "Oat", 85),
            ("milk", "almond", "Almond", 85),
            ("milk", "soy", "Soy", 85),
            ("milk", "coconut", "Coconut", 85),
            ("flavour-shots", "vanilla", "Vanilla", 75),
            ("flavour-shots", "caramel", "Caramel", 75),
            ("flavour-shots", "hazelnut", "Hazelnut", 75),
            ("toast", "plain", "Plain", 0),
            ("toast", "butter", "Butter", 35),
            ("toast", "jam", "House jam", 65),
        ]

        assignments = session.execute(
            select(Product.slug, ModifierGroup.key)
            .select_from(ProductModifierGroup)
            .join(ProductModifierGroup.product)
            .join(ProductModifierGroup.modifier_group)
            .order_by(Product.sort_order, ProductModifierGroup.sort_order)
        ).all()
        assert assignments == [
            ("drip-coffee", "milk"),
            ("cold-brew", "milk"),
            ("cold-brew", "flavour-shots"),
            ("latte", "milk"),
            ("latte", "flavour-shots"),
            ("cappuccino", "milk"),
            ("chai-latte", "milk"),
            ("croissant", "toast"),
        ]


@pytest.mark.postgresql
def test_seed_is_idempotent_and_restores_seed_owned_values(
    seed_engine: Engine,
) -> None:
    with Session(seed_engine) as session:
        seed_catalog(session)
        first_counts = table_counts(session)
        first_ids = {
            product.slug: product.id
            for product in session.scalars(select(Product))
        }

        latte = session.scalar(select(Product).where(Product.slug == "latte"))
        assert latte is not None
        latte.name = "Changed locally"
        session.commit()

        seed_catalog(session)

        assert table_counts(session) == first_counts
        assert {
            product.slug: product.id
            for product in session.scalars(select(Product))
        } == first_ids
        assert session.scalar(
            select(Product.name).where(Product.slug == "latte")
        ) == "Latte"


@pytest.mark.postgresql
def test_seed_does_not_delete_unrelated_data(seed_engine: Engine) -> None:
    with Session(seed_engine) as session:
        unrelated_category = Category(
            organization_id=LADELS_ORGANIZATION_ID,
            slug="staff-specials",
            name="Staff Specials",
            description=None,
            is_published=False,
            sort_order=99,
        )
        unrelated_product = Product(
            organization_id=LADELS_ORGANIZATION_ID,
            category=unrelated_category,
            slug="staff-drink",
            name="Staff Drink",
            description=None,
            base_price_cents=100,
            image_reference=None,
            is_published=False,
            is_featured=False,
            sort_order=99,
        )
        unrelated_product.variants.append(
            ProductVariant(
                key="staff-size",
                name="Staff Size",
                price_cents=100,
                is_active=False,
                sort_order=99,
            )
        )
        unrelated_group = ModifierGroup(
            organization_id=LADELS_ORGANIZATION_ID,
            key="staff-options",
            name="Staff Options",
            description=None,
            selection_type="single",
            is_required=False,
            minimum_selections=0,
            maximum_selections=1,
            is_active=False,
            sort_order=99,
        )
        unrelated_group.options.append(
            ModifierOption(
                key="staff-option",
                name="Staff Option",
                price_adjustment_cents=0,
                is_active=False,
                sort_order=99,
            )
        )
        unrelated_product.modifier_group_assignments.append(
            ProductModifierGroup(
                modifier_group=unrelated_group,
                is_active=False,
                sort_order=99,
            )
        )
        session.add_all([unrelated_category, unrelated_group])
        session.commit()

        seed_catalog(session)

        assert table_counts(session) == (10, 12, 19, 4, 12, 9)
        assert session.scalar(
            select(Product.name).where(Product.slug == "staff-drink")
        ) == "Staff Drink"
        assert session.scalar(
            select(ModifierOption.name).where(
                ModifierOption.key == "staff-option"
            )
        ) == "Staff Option"


@pytest.mark.postgresql
def test_seed_rolls_back_all_changes_on_failure(
    seed_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_seed_products = seed_module._seed_products

    def fail_after_product_writes(*args: object, **kwargs: object) -> None:
        original_seed_products(*args, **kwargs)
        raise RuntimeError("simulated seed failure")

    monkeypatch.setattr(seed_module, "_seed_products", fail_after_product_writes)

    with Session(seed_engine) as session:
        with pytest.raises(RuntimeError, match="simulated seed failure"):
            seed_module.seed_catalog(session)

        assert table_counts(session) == (0, 0, 0, 0, 0, 0)


@pytest.mark.postgresql
def test_invalid_fixture_fails_before_persistence(seed_engine: Engine) -> None:
    invalid_product = replace(
        GUEST_HOUSE_CATALOG.products[0],
        base_price_cents=-1,
    )
    invalid_catalog = replace(
        GUEST_HOUSE_CATALOG,
        products=(invalid_product, *GUEST_HOUSE_CATALOG.products[1:]),
    )

    with Session(seed_engine) as session:
        with pytest.raises(ValueError, match="base price must be nonnegative"):
            seed_catalog(session, invalid_catalog)

        assert table_counts(session) == (0, 0, 0, 0, 0, 0)
