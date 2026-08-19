from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog.models import (
    Category,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductModifierGroup,
    ProductVariant,
    SelectionType,
)
from app.catalog.repository import CatalogRepository
from tests.test_migrations import make_alembic_config
from app.tenancy.resolver import (
    LADELS_ORGANIZATION_ID,
    resolve_internal_ladels_compatibility_context,
)


@pytest.fixture
def catalog_engine(postgresql_url: str) -> Iterator[Engine]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)

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


def make_category(**overrides: object) -> Category:
    values = {
        "organization_id": LADELS_ORGANIZATION_ID,
        "slug": "coffee",
        "name": "Coffee",
        "description": None,
        "is_published": True,
        "sort_order": 0,
    }
    values.update(overrides)
    return Category(**values)


def make_product(category: Category, **overrides: object) -> Product:
    values = {
        "organization_id": LADELS_ORGANIZATION_ID,
        "category": category,
        "slug": "flat-white",
        "name": "Flat White",
        "description": None,
        "base_price_cents": 450,
        "image_reference": None,
        "is_published": True,
        "is_featured": False,
        "is_lunch_special": False,
        "sort_order": 0,
    }
    values.update(overrides)
    return Product(**values)


def make_modifier_group(**overrides: object) -> ModifierGroup:
    values = {
        "organization_id": LADELS_ORGANIZATION_ID,
        "key": "milk",
        "name": "Milk",
        "description": None,
        "selection_type": SelectionType.SINGLE,
        "is_required": True,
        "minimum_selections": 1,
        "maximum_selections": 1,
        "is_active": True,
        "sort_order": 0,
    }
    values.update(overrides)
    return ModifierGroup(**values)


@pytest.mark.postgresql
def test_models_persist_relationships_and_repository_queries(
    catalog_engine: Engine,
) -> None:
    with Session(catalog_engine) as session:
        category = make_category()
        product = make_product(category)
        variant = ProductVariant(
            product=product,
            key="large",
            name="Large",
            price_cents=550,
            is_active=True,
            sort_order=0,
        )
        group = make_modifier_group()
        option = ModifierOption(
            modifier_group=group,
            key="oat",
            name="Oat",
            price_adjustment_cents=75,
            is_active=True,
            sort_order=0,
        )
        assignment = ProductModifierGroup(
            product=product,
            modifier_group=group,
            is_active=True,
            sort_order=0,
        )

        repository = CatalogRepository(
            session, resolve_internal_ladels_compatibility_context(session)
        )
        repository.add(category)
        repository.add(group)
        session.commit()

        assert repository.get_category_by_slug("coffee") is category
        assert repository.get_product_by_slug("flat-white") is product
        assert repository.get_modifier_group_by_key("milk") is group
        assert repository.list_categories() == [category]
        assert product.variants == [variant]
        assert group.options == [option]
        assert product.modifier_group_assignments == [assignment]
        assert assignment.modifier_group is group


@pytest.mark.postgresql
@pytest.mark.parametrize(
    ("model_factory", "expected_message"),
    [
        (lambda: make_category(name="  "), "name must not be blank"),
        (
            lambda: make_product(make_category(), base_price_cents=-1),
            "base_price_cents must be nonnegative",
        ),
        (
            lambda: ProductVariant(
                product=make_product(make_category()),
                key="large",
                name="Large",
                price_cents=-1,
                is_active=True,
                sort_order=0,
            ),
            "price_cents must be nonnegative",
        ),
        (
            lambda: ModifierOption(
                modifier_group=make_modifier_group(),
                key="oat",
                name="Oat",
                price_adjustment_cents=-1,
                is_active=True,
                sort_order=0,
            ),
            "price_adjustment_cents must be nonnegative",
        ),
    ],
)
def test_model_field_validation(
    model_factory: object,
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        model_factory()


@pytest.mark.postgresql
@pytest.mark.parametrize(
    "group",
    [
        make_modifier_group(minimum_selections=0),
        make_modifier_group(
            selection_type=SelectionType.SINGLE,
            maximum_selections=0,
        ),
        make_modifier_group(
            selection_type=SelectionType.MULTIPLE,
            minimum_selections=2,
            maximum_selections=1,
        ),
        make_modifier_group(
            is_required=False,
            minimum_selections=1,
            maximum_selections=1,
        ),
    ],
)
def test_modifier_group_model_rejects_invalid_selection_rules(
    catalog_engine: Engine,
    group: ModifierGroup,
) -> None:
    with Session(catalog_engine) as session:
        session.add(group)
        with pytest.raises(ValueError):
            session.flush()


@pytest.mark.postgresql
def test_single_selection_group_can_allow_quantity_with_total_unit_limit(
    catalog_engine: Engine,
) -> None:
    with Session(catalog_engine) as session:
        group = make_modifier_group(
            selection_type=SelectionType.SINGLE,
            allow_quantity=True,
            maximum_selections=3,
        )
        session.add(group)
        session.flush()
        assert group.maximum_selections == 3


@pytest.mark.postgresql
def test_database_rejects_invalid_constraints(catalog_engine: Engine) -> None:
    invalid_statements = [
        (
            "INSERT INTO categories (organization_id, slug, name, sort_order) "
            f"VALUES ('{LADELS_ORGANIZATION_ID}', 'bad-category', ' ', 0)"
        ),
        (
            "INSERT INTO categories (organization_id, slug, name, sort_order) "
            f"VALUES ('{LADELS_ORGANIZATION_ID}', 'negative-sort', 'Negative', -1)"
        ),
        (
            "INSERT INTO modifier_groups "
            "(organization_id, key, name, selection_type, is_required, minimum_selections, "
            "maximum_selections, sort_order) "
            f"VALUES ('{LADELS_ORGANIZATION_ID}', 'invalid-range', 'Invalid', 'multiple', true, 2, 1, 0)"
        ),
        (
            "INSERT INTO modifier_groups "
            "(organization_id, key, name, selection_type, is_required, minimum_selections, "
            "maximum_selections, allow_quantity, sort_order) "
            f"VALUES ('{LADELS_ORGANIZATION_ID}', 'invalid-single-range', 'Invalid single', 'single', "
            "false, 0, 2, false, 0)"
        ),
    ]

    for statement in invalid_statements:
        with pytest.raises(IntegrityError):
            with catalog_engine.begin() as connection:
                connection.execute(text(statement))


@pytest.mark.postgresql
def test_database_enforces_keys_and_foreign_keys(catalog_engine: Engine) -> None:
    with catalog_engine.begin() as connection:
        category_id = connection.scalar(
            text(
                "INSERT INTO categories (organization_id, slug, name) "
                f"VALUES ('{LADELS_ORGANIZATION_ID}', 'coffee', 'Coffee') "
                "RETURNING id"
            )
        )
        product_id = connection.scalar(
            text(
                "INSERT INTO products "
                "(organization_id, category_id, slug, name, base_price_cents) "
                f"VALUES ('{LADELS_ORGANIZATION_ID}', :category_id, 'latte', 'Latte', 450) RETURNING id"
            ),
            {"category_id": category_id},
        )
        group_id = connection.scalar(
            text(
                "INSERT INTO modifier_groups "
                "(organization_id, key, name, selection_type, is_required, minimum_selections, "
                "maximum_selections) "
                f"VALUES ('{LADELS_ORGANIZATION_ID}', 'milk', 'Milk', 'single', false, 0, 1) RETURNING id"
            )
        )

    duplicate_or_invalid_statements = [
        (
            "INSERT INTO categories (organization_id, slug, name) "
            f"VALUES ('{LADELS_ORGANIZATION_ID}', 'coffee', 'Duplicate')",
            {},
        ),
        (
            "INSERT INTO products "
            "(organization_id, category_id, slug, name, base_price_cents) "
            f"VALUES ('{LADELS_ORGANIZATION_ID}', 999999, 'orphan', 'Orphan', 100)",
            {},
        ),
        (
            "INSERT INTO product_variants "
            "(product_id, key, name, price_cents) "
            "VALUES (:product_id, 'large', 'Large', -1)",
            {"product_id": product_id},
        ),
        (
            "INSERT INTO product_modifier_groups "
            "(product_id, modifier_group_id) "
            "VALUES (:product_id, :group_id), (:product_id, :group_id)",
            {"product_id": product_id, "group_id": group_id},
        ),
    ]

    for statement, parameters in duplicate_or_invalid_statements:
        with pytest.raises(IntegrityError):
            with catalog_engine.begin() as connection:
                connection.execute(text(statement), parameters)


@pytest.mark.postgresql
def test_parent_delete_cascades_catalog_children(catalog_engine: Engine) -> None:
    with Session(catalog_engine) as session:
        category = make_category()
        product = make_product(category)
        product.variants.append(
            ProductVariant(
                key="large",
                name="Large",
                price_cents=550,
                is_active=True,
                sort_order=0,
            )
        )
        group = make_modifier_group()
        group.options.append(
            ModifierOption(
                key="oat",
                name="Oat",
                price_adjustment_cents=75,
                is_active=True,
                sort_order=0,
            )
        )
        product.modifier_group_assignments.append(
            ProductModifierGroup(modifier_group=group, is_active=True, sort_order=0)
        )
        session.add_all([category, group])
        session.commit()

        session.delete(product)
        session.commit()

        assert session.scalar(text("SELECT count(*) FROM product_variants")) == 0
        assert session.scalar(text("SELECT count(*) FROM product_modifier_groups")) == 0
        assert session.scalar(text("SELECT count(*) FROM modifier_options")) == 1
