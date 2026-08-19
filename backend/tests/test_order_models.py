from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

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
    ProductVariant,
    SelectionType,
)
from app.orders.constants import OrderStatus
from app.orders.models import Order, OrderItem, OrderItemModifier
from app.orders.repository import OrderRepository
from app.tenancy.resolver import LADELS_ORGANIZATION_ID, resolve_internal_ladels_compatibility_context
from tests.test_migrations import make_alembic_config


@pytest.fixture
def order_engine(postgresql_url: str) -> Iterator[Engine]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)

    def reset_tables() -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE order_item_modifiers, order_items, orders, "
                    "product_availability_overrides, product_availability, "
                    "business_closures, business_hours, business_settings, "
                    "product_modifier_groups, modifier_options, "
                    "product_variants, products, modifier_groups, categories "
                    "RESTART IDENTITY CASCADE"
                )
            )

    reset_tables()
    try:
        yield engine
    finally:
        reset_tables()
        engine.dispose()


def make_order(now: datetime) -> Order:
    return Order(
        organization_id=LADELS_ORGANIZATION_ID,
        idempotency_key="order-key-123",
        request_fingerprint="a" * 64,
        public_access_token="public-token-123",
        status=OrderStatus.PENDING,
        guest_name="Jessie Guest",
        guest_email="jessie@example.com",
        guest_phone="+15551234567",
        notes="Extra hot",
        requested_pickup_at=now + timedelta(hours=1),
        business_timezone="America/New_York",
        currency="USD",
        subtotal_cents=1620,
        tax_cents=0,
        total_cents=1620,
        version=1,
        expires_at=now + timedelta(minutes=30),
        created_at=now,
        updated_at=now,
    )


@pytest.mark.postgresql
def test_order_models_persist_complete_snapshot_relationships(
    order_engine: Engine,
) -> None:
    now = datetime(2026, 7, 28, 12, tzinfo=timezone.utc)
    with Session(order_engine) as session:
        category = Category(
            organization_id=LADELS_ORGANIZATION_ID,
            slug="espresso",
            name="Espresso",
            description=None,
            is_published=True,
            sort_order=0,
        )
        product = Product(
            organization_id=LADELS_ORGANIZATION_ID,
            category=category,
            slug="latte",
            name="Latte",
            description=None,
            base_price_cents=525,
            image_reference=None,
            is_published=True,
            is_featured=True,
            sort_order=0,
        )
        variant = ProductVariant(
            product=product,
            key="large",
            name="Large",
            price_cents=650,
            is_active=True,
            sort_order=0,
        )
        group = ModifierGroup(
            organization_id=LADELS_ORGANIZATION_ID,
            key="milk",
            name="Milk",
            description=None,
            selection_type=SelectionType.SINGLE,
            is_required=True,
            minimum_selections=1,
            maximum_selections=1,
            is_active=True,
            sort_order=0,
        )
        option = ModifierOption(
            modifier_group=group,
            key="oat",
            name="Oat",
            price_adjustment_cents=85,
            is_active=True,
            sort_order=0,
        )
        session.add_all([category, group])
        session.flush()

        order = make_order(now)
        item = OrderItem(
            source_product_id=product.id,
            source_variant_id=variant.id,
            product_slug=product.slug,
            product_name=product.name,
            variant_key=variant.key,
            variant_name=variant.name,
            base_unit_price_cents=650,
            unit_price_cents=810,
            quantity=2,
            line_subtotal_cents=1620,
            sort_order=0,
        )
        item.modifiers.append(
            OrderItemModifier(
                source_modifier_group_id=group.id,
                source_modifier_option_id=option.id,
                modifier_group_key=group.key,
                modifier_group_name=group.name,
                modifier_option_key=option.key,
                modifier_option_name=option.name,
                price_adjustment_cents=160,
                sort_order=0,
            )
        )
        order.items.append(item)
        session.add(order)
        session.commit()

        persisted = OrderRepository(session, resolve_internal_ladels_compatibility_context(session)).get_by_idempotency_key(
            "order-key-123"
        )
        assert persisted is order
        assert persisted.items == [item]
        assert item.modifiers[0].modifier_option_name == "Oat"


@pytest.mark.postgresql
def test_source_catalog_deletion_preserves_order_snapshots(
    order_engine: Engine,
) -> None:
    now = datetime(2026, 7, 28, 12, tzinfo=timezone.utc)
    with Session(order_engine) as session:
        category = Category(
            organization_id=LADELS_ORGANIZATION_ID,
            slug="bakery",
            name="Bakery",
            description=None,
            is_published=True,
            sort_order=0,
        )
        product = Product(
            organization_id=LADELS_ORGANIZATION_ID,
            category=category,
            slug="croissant",
            name="Croissant",
            description=None,
            base_price_cents=425,
            image_reference=None,
            is_published=True,
            is_featured=True,
            sort_order=0,
        )
        session.add(product)
        session.flush()
        order = make_order(now)
        order.subtotal_cents = 425
        order.total_cents = 425
        order.items.append(
            OrderItem(
                source_product_id=product.id,
                source_variant_id=None,
                product_slug="croissant",
                product_name="Croissant",
                variant_key=None,
                variant_name=None,
                base_unit_price_cents=425,
                unit_price_cents=425,
                quantity=1,
                line_subtotal_cents=425,
                sort_order=0,
            )
        )
        session.add(order)
        session.commit()

        session.delete(product)
        session.commit()
        session.refresh(order.items[0])

        assert order.items[0].source_product_id is None
        assert order.items[0].product_name == "Croissant"
        assert order.items[0].unit_price_cents == 425


@pytest.mark.postgresql
def test_database_constraints_reject_invalid_order_totals_and_lines(
    order_engine: Engine,
) -> None:
    now = datetime(2026, 7, 28, 12, tzinfo=timezone.utc)
    with order_engine.begin() as connection:
        order_id = connection.scalar(
            text(
                "INSERT INTO orders "
                "(organization_id, idempotency_key, request_fingerprint, public_access_token, "
                "guest_name, guest_email, guest_phone, requested_pickup_at, "
                "business_timezone, subtotal_cents, tax_cents, total_cents, "
                "expires_at, created_at, updated_at) VALUES "
                "(:organization_id, 'valid-key', :fingerprint, 'valid-token', 'Guest', "
                "'guest@example.com', '+15551234567', :pickup, "
                "'America/New_York', 500, 0, 500, :expires, :now, :now) "
                "RETURNING id"
            ),
            {
                "organization_id": LADELS_ORGANIZATION_ID,
                "fingerprint": "a" * 64,
                "pickup": now + timedelta(hours=1),
                "expires": now + timedelta(minutes=30),
                "now": now,
            },
        )

    invalid_statements = [
        (
            "INSERT INTO orders "
            "(organization_id, idempotency_key, request_fingerprint, public_access_token, "
            "guest_name, guest_email, guest_phone, requested_pickup_at, "
            "business_timezone, subtotal_cents, tax_cents, total_cents, "
            "expires_at, created_at, updated_at) VALUES "
            "(:organization_id, 'bad-total', :fingerprint, 'bad-total-token', 'Guest', "
            "'guest@example.com', '+15551234567', :pickup, "
            "'America/New_York', 500, 0, 499, :expires, :now, :now)",
            {
                "organization_id": LADELS_ORGANIZATION_ID,
                "fingerprint": "b" * 64,
                "pickup": now + timedelta(hours=1),
                "expires": now + timedelta(minutes=30),
                "now": now,
            },
        ),
        (
            "INSERT INTO order_items "
            "(order_id, product_slug, product_name, base_unit_price_cents, "
            "unit_price_cents, quantity, line_subtotal_cents, sort_order) "
            "VALUES (:order_id, 'latte', 'Latte', 500, 500, 2, 999, 0)",
            {"order_id": order_id},
        ),
    ]

    for statement, parameters in invalid_statements:
        with pytest.raises(IntegrityError):
            with order_engine.begin() as connection:
                connection.execute(text(statement), parameters)


def test_order_models_reject_invalid_fields_before_persistence() -> None:
    now = datetime(2026, 7, 28, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="guest_name must not be blank"):
        make_order(now).guest_name = " "

    with pytest.raises(ValueError, match="quantity must be between"):
        OrderItem(
            source_product_id=None,
            source_variant_id=None,
            product_slug="latte",
            product_name="Latte",
            variant_key=None,
            variant_name=None,
            base_unit_price_cents=500,
            unit_price_cents=500,
            quantity=0,
            line_subtotal_cents=0,
            sort_order=0,
        )
