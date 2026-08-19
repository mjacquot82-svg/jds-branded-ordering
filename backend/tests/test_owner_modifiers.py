from collections.abc import Iterator

import pytest
from alembic import command
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.catalog.models import Category, ModifierGroup, ModifierOption, Product
from app.catalog.repository import CatalogRepository
from app.catalog.schemas import OwnerModifierGroupWrite, OwnerModifierOptionWrite, OwnerProductWrite
from app.catalog.service import CatalogService
from tests.test_migrations import make_alembic_config


@pytest.fixture
def modifier_engine(postgresql_url: str) -> Iterator[Engine]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    with engine.begin() as connection:
        connection.execute(text(
            "TRUNCATE product_modifier_groups, modifier_options, product_variants, "
            "product_availability, products, modifier_groups, categories RESTART IDENTITY CASCADE"
        ))
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text(
                "TRUNCATE product_modifier_groups, modifier_options, product_variants, "
                "product_availability, products, modifier_groups, categories RESTART IDENTITY CASCADE"
            ))
        engine.dispose()


def group_write(**changes: object) -> OwnerModifierGroupWrite:
    values = dict(
        name="Milk", description="", selection_type="single", required=False,
        min_selections=0, max_selections=1, active=True, sort_order=0,
    )
    values.update(changes)
    return OwnerModifierGroupWrite(**values)


def option_write(**changes: object) -> OwnerModifierOptionWrite:
    values = dict(name="Regular milk", price_adjustment_cents=0, active=True, sort_order=0)
    values.update(changes)
    return OwnerModifierOptionWrite(**values)


@pytest.mark.postgresql
def test_owner_manages_group_options_assignments_and_public_runtime_catalog(
    modifier_engine: Engine,
) -> None:
    with Session(modifier_engine) as session:
        category = Category(slug="test-coffee", name="Test coffee", is_published=True, sort_order=0)
        product = Product(
            category=category, slug="test-coffee", name="Test coffee", description="",
            base_price_cents=400, image_reference="", is_published=True,
            is_featured=False, is_lunch_special=False, sort_order=0,
        )
        session.add(category)
        session.commit()
        service = CatalogService(CatalogRepository(session), tax_name="HST", tax_rate_millionths=1_300_000)

        created = service.create_modifier_group(group_write())
        assert created.name == "Milk"
        assert created.options == []
        group_id = int(created.id)

        regular = service.create_modifier_option(group_id, option_write())
        oat = service.create_modifier_option(group_id, option_write(
            name="Oat milk", price_adjustment_cents=75, sort_order=1,
        ))
        assert regular.price_adjustment_cents == 0
        assert oat.price_adjustment_cents == 75

        required = service.update_modifier_group(group_id, group_write(
            name="Milk choice", required=True, min_selections=1,
        ))
        assert required.required is True
        assert required.min_selections == 1

        product_payload = OwnerProductWrite(
            slug=product.slug, name=product.name, base_price_cents=product.base_price_cents,
            category_id=category.id, modifier_group_ids=[group_id],
        )
        updated = service.update_product(product.id, product_payload)
        assert updated.modifier_group_ids == [str(group_id)]

        public = service.build_catalog()
        public_group = public.categories[0].products[0].modifier_groups[0]
        assert public_group.name == "Milk choice"
        assert public_group.required is True
        assert [(item.name, item.price_adjustment_cents) for item in public_group.options] == [
            ("Regular milk", 0), ("Oat milk", 75),
        ]

        service.update_modifier_option(group_id, int(oat.id), option_write(
            name="Oat beverage", price_adjustment_cents=100, active=False, sort_order=1,
        ))
        public = service.build_catalog()
        assert [item.name for item in public.categories[0].products[0].modifier_groups[0].options] == ["Regular milk"]

        product_payload.modifier_group_ids = []
        assert service.update_product(product.id, product_payload).modifier_group_ids == []
        assert service.build_catalog().categories[0].products[0].modifier_groups == []


@pytest.mark.postgresql
def test_disabled_group_and_option_are_preserved_for_owner_but_excluded_publicly(
    modifier_engine: Engine,
) -> None:
    with Session(modifier_engine) as session:
        service = CatalogService(CatalogRepository(session), tax_name="HST", tax_rate_millionths=1_300_000)
        created = service.create_modifier_group(group_write(active=False))
        option = service.create_modifier_option(int(created.id), option_write(active=False))
        owner = service.build_owner_catalog().modifier_groups[0]
        assert owner.active is False
        assert owner.options[0].id == option.id
        assert owner.options[0].active is False


@pytest.mark.postgresql
def test_modifier_validation_and_duplicate_assignment_prevention(
    modifier_engine: Engine,
) -> None:
    with Session(modifier_engine) as session:
        service = CatalogService(CatalogRepository(session))
        with pytest.raises(ValueError, match="minimum"):
            service.create_modifier_group(group_write(required=True, min_selections=0))
        with pytest.raises(ValueError, match="Maximum"):
            service.create_modifier_group(group_write(
                selection_type="multiple", required=True, min_selections=2, max_selections=1,
            ))
        with pytest.raises(ValidationError):
            OwnerModifierOptionWrite(name="Invalid", price_adjustment_cents=-1)

        category = Category(slug="coffee", name="Coffee", is_published=True, sort_order=0)
        product = Product(
            category=category, slug="coffee", name="Coffee", base_price_cents=300,
            is_published=True, is_featured=False, is_lunch_special=False, sort_order=0,
        )
        session.add(category); session.commit()
        group = service.create_modifier_group(group_write())
        service.create_modifier_option(int(group.id), option_write())
        payload = OwnerProductWrite(
            slug="coffee", name="Coffee", base_price_cents=300,
            category_id=category.id, modifier_group_ids=[int(group.id), int(group.id)],
        )
        with pytest.raises(ValueError, match="unique"):
            service.update_product(product.id, payload)


@pytest.mark.postgresql
def test_assigned_required_group_cannot_be_made_impossible(
    modifier_engine: Engine,
) -> None:
    with Session(modifier_engine) as session:
        service = CatalogService(CatalogRepository(session))
        category = Category(slug="coffee", name="Coffee", is_published=True, sort_order=0)
        product = Product(
            category=category, slug="coffee", name="Coffee", base_price_cents=300,
            is_published=True, is_featured=False, is_lunch_special=False, sort_order=0,
        )
        session.add(category); session.commit()
        group = service.create_modifier_group(group_write(required=True, min_selections=1))
        option = service.create_modifier_option(int(group.id), option_write())
        service.update_product(product.id, OwnerProductWrite(
            slug="coffee", name="Coffee", base_price_cents=300,
            category_id=category.id, modifier_group_ids=[int(group.id)],
        ))
        with pytest.raises(ValueError, match="enabled options"):
            service.update_modifier_option(int(group.id), int(option.id), option_write(active=False))
        archived = service.update_modifier_group(int(group.id), group_write(
            required=True, min_selections=1, active=False,
        ))
        assert archived.active is False
        assert session.scalar(select(ModifierGroup)).product_assignments
        assert session.scalar(select(ModifierOption)).is_active is True
