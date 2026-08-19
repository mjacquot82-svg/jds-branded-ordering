from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.availability.models import ProductAvailability
from app.catalog.models import (
    Category,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductModifierGroup,
    ProductVariant,
    SelectionType,
)
from app.customers.repository import CustomerRepository
from app.db.base import Base
from app.orders.models import Order, OrderItem, OrderItemModifier
from app.jds_auth.models import Organization
from app.tenancy.resolver import (
    LADELS_ORGANIZATION_ID,
    LADELS_ORGANIZATION_NAME,
    LADELS_ORGANIZATION_SLUG,
)
from app.tenancy.context import TenantContext, TenantResolutionSource


TENANT = TenantContext(
    organization_id=LADELS_ORGANIZATION_ID,
    organization_slug=LADELS_ORGANIZATION_SLUG,
    source=TenantResolutionSource.LADELS_COMPATIBILITY,
)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def sqlite_functions(connection, _):
        connection.create_function("btrim", 1, lambda value: value.strip() if value else value)
        connection.create_function("char_length", 1, lambda value: len(value) if value is not None else None)

    Base.metadata.create_all(engine)
    # SQLite does not honor the PostgreSQL-only partial-index predicate.
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX uq_products_single_lunch_special"))
    with Session(engine) as session, session.begin():
        session.add(
            Organization(
                id=LADELS_ORGANIZATION_ID,
                slug=LADELS_ORGANIZATION_SLUG,
                name=LADELS_ORGANIZATION_NAME,
            )
        )
    return engine


def _order(session, *, order_id, customer_id, status, fulfillment="new", created_at, product_id, quantity):
    order = Order(
        organization_id=LADELS_ORGANIZATION_ID,
        id=order_id,
        customer_user_id=customer_id,
        idempotency_key=f"quick-order-{order_id}",
        request_fingerprint=f"{order_id:064d}"[-64:],
        public_access_token=f"quick-order-token-{order_id}",
        status=status,
        fulfillment_status=fulfillment,
        guest_name="Customer",
        guest_email="customer@example.com",
        guest_phone="+15195550123",
        requested_pickup_at=created_at + timedelta(minutes=20),
        business_timezone="America/Toronto",
        currency="CAD",
        subtotal_cents=500 * quantity,
        tax_cents=0,
        total_cents=500 * quantity,
        version=1,
        expires_at=created_at + timedelta(hours=1),
        created_at=created_at,
        updated_at=created_at,
    )
    order.items.append(OrderItem(
        id=order_id,
        source_product_id=product_id,
        product_slug=f"product-{product_id}",
        product_name=f"Product {product_id}",
        base_unit_price_cents=500,
        unit_price_cents=500,
        quantity=quantity,
        line_subtotal_cents=500 * quantity,
        sort_order=0,
        created_at=created_at,
    ))
    session.add(order)


def test_quick_order_uses_paid_quantity_recency_customer_ownership_and_current_catalog():
    engine = _engine()
    customer_id = uuid4()
    other_customer_id = uuid4()
    now = datetime.now(timezone.utc)

    with Session(engine) as session, session.begin():
        public = Category(id=1, organization_id=LADELS_ORGANIZATION_ID, slug="public", name="Public", is_published=True)
        hidden = Category(id=2, organization_id=LADELS_ORGANIZATION_ID, slug="hidden", name="Hidden", is_published=False)
        session.add_all([public, hidden])
        for product_id in range(1, 12):
            session.add(Product(
                id=product_id,
                organization_id=LADELS_ORGANIZATION_ID,
                category_id=2 if product_id == 11 else 1,
                slug=f"product-{product_id}",
                name=f"Product {product_id}",
                base_price_cents=500,
                is_published=product_id != 10,
                archived_at=now if product_id == 9 else None,
            ))
        session.add(
            ProductAvailability(
                organization_id=LADELS_ORGANIZATION_ID,
                product_id=8,
                default_available=False,
            )
        )

        # Equal total quantity: product 3 wins the recency tie over product 1.
        _order(session, order_id=1, customer_id=customer_id, status="paid", created_at=now - timedelta(days=10), product_id=1, quantity=5)
        _order(session, order_id=2, customer_id=customer_id, status="paid", fulfillment="completed", created_at=now - timedelta(days=5), product_id=2, quantity=3)
        _order(session, order_id=3, customer_id=customer_id, status="paid", fulfillment="ready", created_at=now - timedelta(days=1), product_id=3, quantity=5)

        # Non-purchases, cancellation, another customer, and non-public products never rank.
        _order(session, order_id=4, customer_id=customer_id, status="payment_failed", created_at=now, product_id=4, quantity=50)
        _order(session, order_id=5, customer_id=customer_id, status="payment_pending", created_at=now, product_id=5, quantity=50)
        _order(session, order_id=6, customer_id=customer_id, status="paid", fulfillment="cancelled", created_at=now, product_id=6, quantity=50)
        _order(session, order_id=7, customer_id=other_customer_id, status="paid", created_at=now, product_id=7, quantity=50)
        _order(session, order_id=8, customer_id=customer_id, status="paid", created_at=now, product_id=8, quantity=50)
        _order(session, order_id=9, customer_id=customer_id, status="paid", created_at=now, product_id=9, quantity=50)
        _order(session, order_id=10, customer_id=customer_id, status="paid", created_at=now, product_id=10, quantity=50)
        _order(session, order_id=11, customer_id=customer_id, status="paid", created_at=now, product_id=11, quantity=50)

    with Session(engine) as session:
        assert CustomerRepository(session, TENANT).quick_order_product_ids(customer_id) == [3, 1, 2]
        assert CustomerRepository(session, TENANT).quick_order_product_ids(uuid4()) == []


def test_quick_order_is_capped_at_six_with_a_deterministic_product_id_tie_break():
    engine = _engine()
    customer_id = uuid4()
    now = datetime.now(timezone.utc)

    with Session(engine) as session, session.begin():
        session.add(Category(id=1, organization_id=LADELS_ORGANIZATION_ID, slug="public", name="Public", is_published=True))
        for product_id in range(1, 9):
            session.add(Product(id=product_id, organization_id=LADELS_ORGANIZATION_ID, category_id=1, slug=f"product-{product_id}", name=f"Product {product_id}", base_price_cents=500, is_published=True))
            _order(session, order_id=product_id, customer_id=customer_id, status="paid", created_at=now, product_id=product_id, quantity=1)

    with Session(engine) as session:
        assert CustomerRepository(session, TENANT).quick_order_product_ids(customer_id) == [1, 2, 3, 4, 5, 6]


def test_exact_quick_order_preserves_quantity_and_uses_only_current_valid_catalog_price():
    engine = _engine()
    customer_id = uuid4()
    now = datetime.now(timezone.utc)

    with Session(engine) as session, session.begin():
        category = Category(id=1, organization_id=LADELS_ORGANIZATION_ID, slug="coffee", name="Coffee", is_published=True)
        product = Product(
            id=1, organization_id=LADELS_ORGANIZATION_ID, category=category, slug="drip-coffee", name="Drip Coffee",
            base_price_cents=190, is_published=True,
        )
        variant = ProductVariant(
            id=20, product=product, key="12oz", name="12oz",
            price_cents=205, is_active=True,
        )
        milk = ModifierGroup(
            id=30, organization_id=LADELS_ORGANIZATION_ID, key="milk", name="Milk", selection_type=SelectionType.SINGLE,
            is_required=True, minimum_selections=1, maximum_selections=1,
            allow_quantity=False, is_active=True,
        )
        whole = ModifierOption(
            id=31, modifier_group=milk, key="whole-milk", name="Whole milk",
            price_adjustment_cents=0, is_active=True,
        )
        sugar = ModifierGroup(
            id=40, organization_id=LADELS_ORGANIZATION_ID, key="sugar", name="Sugar", selection_type=SelectionType.SINGLE,
            is_required=True, minimum_selections=1, maximum_selections=5,
            allow_quantity=True, is_active=True,
        )
        sugar_option = ModifierOption(
            id=41, modifier_group=sugar, key="sugar", name="Sugar",
            price_adjustment_cents=5, is_active=True,
        )
        product.modifier_group_assignments = [
            ProductModifierGroup(modifier_group=milk, is_active=True, sort_order=0),
            ProductModifierGroup(modifier_group=sugar, is_active=True, sort_order=1),
        ]
        order = Order(
            organization_id=LADELS_ORGANIZATION_ID,
            id=1, customer_user_id=customer_id, idempotency_key="exact-quick-order",
            request_fingerprint="1" * 64, public_access_token="exact-quick-token",
            status="paid", fulfillment_status="completed", guest_name="Quick Customer",
            guest_email="quick@example.com", guest_phone="+15195550123",
            requested_pickup_at=now, business_timezone="America/Toronto", currency="CAD",
            subtotal_cents=999, tax_cents=0, total_cents=999, version=1,
            expires_at=now + timedelta(hours=1), created_at=now, updated_at=now,
        )
        order.items.append(OrderItem(
            id=1, source_product_id=1, source_variant_id=20,
            product_slug="drip-coffee", product_name="Drip Coffee",
            variant_key="12oz", variant_name="12oz", base_unit_price_cents=999,
            unit_price_cents=999, quantity=1, line_subtotal_cents=999, sort_order=0,
            modifiers=[
                OrderItemModifier(
                    id=1,
                    source_modifier_group_id=30, source_modifier_option_id=31,
                    modifier_group_key="milk", modifier_group_name="Milk",
                    modifier_option_key="whole-milk", modifier_option_name="Whole milk",
                    price_adjustment_cents=0, quantity=1, sort_order=0,
                ),
                OrderItemModifier(
                    id=2,
                    source_modifier_group_id=40, source_modifier_option_id=41,
                    modifier_group_key="sugar", modifier_group_name="Sugar",
                    modifier_option_key="sugar", modifier_option_name="Sugar",
                    price_adjustment_cents=0, quantity=2, sort_order=1,
                ),
            ],
        ))
        session.add_all([product, variant, whole, sugar_option, order])

    with Session(engine) as session:
        assert CustomerRepository(session, TENANT).quick_order_configurations(customer_id) == [{
            "product_id": "1",
            "variant_id": "20",
            "modifiers": [
                {"option_id": "31", "option_name": "Whole milk", "quantity": 1},
                {"option_id": "41", "option_name": "Sugar", "quantity": 2},
            ],
            "unit_price_cents": 215,
        }]
        session.get(ModifierOption, 41).is_active = False
        session.commit()

    with Session(engine) as session:
        assert CustomerRepository(session, TENANT).quick_order_configurations(customer_id) == []
