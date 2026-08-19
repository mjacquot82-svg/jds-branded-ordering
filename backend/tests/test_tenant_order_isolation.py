from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.catalog.models import Category, ModifierGroup, ModifierOption, Product, SelectionType
from app.availability.models import BusinessSettings
from app.customers.repository import CustomerRepository
from app.jds_auth.models import JdsUser, Organization
from app.orders.constants import FulfillmentStatus, OrderStatus
from app.orders.fulfillment import FulfillmentError, FulfillmentErrorCode, OwnerOrderService
from app.orders.models import Order, OrderItem
from app.orders.repository import OrderRepository
from app.orders.schemas import ConfiguredOrderLineInput
from app.orders.service import OrderCreationError, OrderCreationErrorCode, OrderCreationService
from app.tenancy.resolver import LADELS_ORGANIZATION_SLUG, resolve_owner_tenant_context
from tests.test_migrations import make_alembic_config
from tests.test_order_service import local_datetime, make_request, seed_order_dependencies


@pytest.fixture
def tenant_order_engine(postgresql_url: str) -> Iterator[Engine]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    with engine.begin() as connection:
        connection.execute(text(
            "TRUNCATE customer_loyalty_events, order_item_modifiers, order_items, orders, "
            "product_availability_overrides, product_availability, business_closures, "
            "business_hours, business_settings, product_modifier_groups, modifier_options, "
            "product_variants, products, modifier_groups, categories RESTART IDENTITY CASCADE"
        ))
        connection.execute(text("DELETE FROM organizations WHERE slug = 'order-tenant-b'"))
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text(
                "TRUNCATE customer_loyalty_events, order_item_modifiers, order_items, orders, "
                "product_availability_overrides, product_availability, business_closures, "
                "business_hours, business_settings, product_modifier_groups, modifier_options, "
                "product_variants, products, modifier_groups, categories RESTART IDENTITY CASCADE"
            ))
            connection.execute(text("DELETE FROM organizations WHERE slug = 'order-tenant-b'"))
        engine.dispose()


def contexts(session: Session):
    tenant_a_org = session.scalar(select(Organization).where(Organization.slug == LADELS_ORGANIZATION_SLUG))
    tenant_b_org = Organization(id=uuid4(), slug="order-tenant-b", name="Order Tenant B")
    session.add(tenant_b_org)
    session.flush()
    return (
        resolve_owner_tenant_context(session, principal_organization_id=tenant_a_org.id),
        resolve_owner_tenant_context(session, principal_organization_id=tenant_b_org.id),
    )


def order_for(organization_id, *, key: str, customer_id=None, fulfillment=FulfillmentStatus.NEW) -> Order:
    now = datetime.now(timezone.utc)
    return Order(
        organization_id=organization_id, customer_user_id=customer_id,
        idempotency_key=key, request_fingerprint=key[0] * 64,
        public_access_token="colliding-public-token", status=OrderStatus.PAID,
        fulfillment_status=fulfillment, guest_name="Guest", guest_email="guest@example.com",
        guest_phone="+15195550123", requested_pickup_at=now + timedelta(minutes=20),
        business_timezone="America/Toronto", currency="CAD", subtotal_cents=500,
        tax_cents=0, total_cents=500, version=1, expires_at=now + timedelta(hours=1),
        items=[OrderItem(product_slug="latte", product_name="Latte", base_unit_price_cents=500,
                         unit_price_cents=500, quantity=1, line_subtotal_cents=500, sort_order=0)],
    )


@pytest.mark.postgresql
def test_order_reads_queues_history_counts_and_mutations_are_tenant_isolated(tenant_order_engine: Engine) -> None:
    with Session(tenant_order_engine) as session:
        tenant_a, tenant_b = contexts(session)
        customer_id = uuid4()
        session.add(JdsUser(id=customer_id, primary_email=f"{customer_id}@example.com", display_name="Shared Customer"))
        session.add_all([
            BusinessSettings(organization_id=tenant_a.organization_id, timezone="UTC"),
            BusinessSettings(organization_id=tenant_b.organization_id, timezone="UTC"),
        ])
        order_a = order_for(tenant_a.organization_id, key="same-key", customer_id=customer_id)
        order_b = order_for(tenant_b.organization_id, key="same-key", customer_id=customer_id)
        session.add_all([order_a, order_b])
        session.commit()

        repository_a = OrderRepository(session, tenant_a)
        repository_b = OrderRepository(session, tenant_b)
        assert repository_a.get_by_idempotency_key("same-key") is order_a
        assert repository_b.get_by_idempotency_key("same-key") is order_b
        assert repository_a.get_by_public_access_token(
            "colliding-public-token", customer_user_id=customer_id
        ) is order_a
        assert repository_b.get_by_public_access_token(
            "colliding-public-token", customer_user_id=customer_id
        ) is order_b
        assert repository_a.get_complete(order_b.id) is None
        assert repository_a.active_orders(unpaid_cutoff=datetime.now(timezone.utc) - timedelta(days=1)) == [order_a]
        assert CustomerRepository(session, tenant_a).orders(customer_id) == [order_a]
        assert CustomerRepository(session, tenant_a).order(customer_id, order_b.id) is None
        assert OwnerOrderService(session, tenant_a).dashboard(now=datetime.now(timezone.utc))["active_paid"] == 1
        with pytest.raises(FulfillmentError) as error:
            OwnerOrderService(session, tenant_a).transition(
                order_b.id, target=FulfillmentStatus.COMPLETED,
                expected_version=1, now=datetime.now(timezone.utc)
            )
        assert error.value.code == FulfillmentErrorCode.NOT_FOUND
        session.refresh(order_b)
        assert order_b.fulfillment_status == FulfillmentStatus.NEW


@pytest.mark.postgresql
def test_repository_write_and_order_creation_fail_closed_across_tenants(tenant_order_engine: Engine) -> None:
    with Session(tenant_order_engine) as session:
        ids = seed_order_dependencies(session)
        tenant_a, tenant_b = contexts(session)
        foreign_category = Category(organization_id=tenant_b.organization_id, slug="coffee", name="Coffee", is_published=True)
        foreign_product = Product(organization_id=tenant_b.organization_id, category=foreign_category,
                                  slug="latte", name="Tenant B Latte", base_price_cents=500, is_published=True)
        foreign_group = ModifierGroup(organization_id=tenant_b.organization_id, key="milk", name="Milk",
                                      selection_type=SelectionType.SINGLE, minimum_selections=0,
                                      maximum_selections=1, is_active=True)
        foreign_option = ModifierOption(modifier_group=foreign_group, key="oat", name="Oat",
                                        price_adjustment_cents=0, is_active=True)
        session.add_all([foreign_category, foreign_product, foreign_group])
        session.commit()

        with pytest.raises(ValueError, match="another organization"):
            OrderRepository(session, tenant_a).add(order_for(tenant_b.organization_id, key="foreign"))

        foreign_product_id = foreign_product.id
        foreign_option_id = foreign_option.id
        session.rollback()
        foreign_product_request = make_request(ids, lines=[ConfiguredOrderLineInput(
            product_id=foreign_product_id, variant_id=None, modifier_option_ids=[], quantity=1
        )])
        with pytest.raises(OrderCreationError) as product_error:
            OrderCreationService(session, tenant_a).create_pending_order(foreign_product_request, now=local_datetime(8))
        assert product_error.value.code == OrderCreationErrorCode.PRODUCT_NOT_SELLABLE

        foreign_modifier_request = make_request(ids, lines=[ConfiguredOrderLineInput(
            product_id=ids["product"], variant_id=ids["large"],
            modifier_option_ids=[ids["oat"], foreign_option_id], quantity=1
        )])
        with pytest.raises(OrderCreationError) as modifier_error:
            OrderCreationService(session, tenant_a).create_pending_order(foreign_modifier_request, now=local_datetime(8))
        assert modifier_error.value.code == OrderCreationErrorCode.MODIFIER_OPTION_INVALID


@pytest.mark.postgresql
def test_completion_and_cancellation_remain_independent_between_tenants(tenant_order_engine: Engine) -> None:
    with Session(tenant_order_engine) as session:
        tenant_a, tenant_b = contexts(session)
        completed_a = order_for(tenant_a.organization_id, key="complete")
        cancelled_b = order_for(tenant_b.organization_id, key="cancel")
        session.add_all([completed_a, cancelled_b])
        session.commit()
        OwnerOrderService(session, tenant_a).transition(completed_a.id, target=FulfillmentStatus.COMPLETED,
                                                        expected_version=1, now=datetime.now(timezone.utc))
        OwnerOrderService(session, tenant_b).transition(cancelled_b.id, target=FulfillmentStatus.CANCELLED,
                                                        expected_version=1, now=datetime.now(timezone.utc))
        assert OrderRepository(session, tenant_a).history() == [completed_a]
        assert OrderRepository(session, tenant_b).history() == [cancelled_b]
