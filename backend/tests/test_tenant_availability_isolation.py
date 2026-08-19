from collections.abc import Iterator
from datetime import date, datetime, time, timezone
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.owner_scheduling import ClosureWrite, save_closure
from app.availability.models import (
    BusinessClosure,
    BusinessHour,
    BusinessSettings,
    ProductAvailability,
    ProductAvailabilityOverride,
)
from app.availability.repository import AvailabilityRepository
from app.availability.service import PickupSchedulingService, SellabilityService
from app.catalog.models import Category, Product
from app.jds_auth.models import Organization
from app.tenancy.resolver import (
    LADELS_ORGANIZATION_SLUG,
    resolve_owner_tenant_context,
)
from tests.test_migrations import make_alembic_config


@pytest.fixture
def tenant_availability_engine(postgresql_url: str) -> Iterator[Engine]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)

    def reset() -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE product_availability_overrides, product_availability, "
                    "products, categories, business_closures, business_hours, "
                    "business_settings RESTART IDENTITY CASCADE"
                )
            )
            connection.execute(
                text("DELETE FROM organizations WHERE slug = 'availability-tenant-b'")
            )

    reset()
    try:
        yield engine
    finally:
        reset()
        engine.dispose()


def tenant_contexts(session: Session):
    tenant_a = session.scalar(
        select(Organization).where(Organization.slug == LADELS_ORGANIZATION_SLUG)
    )
    tenant_b = Organization(
        id=uuid4(), slug="availability-tenant-b", name="Availability Tenant B"
    )
    session.add(tenant_b)
    session.flush()
    return (
        resolve_owner_tenant_context(
            session, principal_organization_id=tenant_a.id
        ),
        resolve_owner_tenant_context(
            session, principal_organization_id=tenant_b.id
        ),
    )


def scheduling_records(context, *, lead_time: int, closed: bool):
    settings = BusinessSettings(
        organization_id=context.organization_id,
        timezone="UTC",
        minimum_lead_time_minutes=lead_time,
        pickup_interval_minutes=5,
        maximum_advance_days=14,
    )
    hour = BusinessHour(
        organization_id=context.organization_id,
        settings=settings,
        weekday=0,
        is_closed=closed,
        opens_at=None if closed else time(8),
        closes_at=None if closed else time(17),
    )
    closure = BusinessClosure(
        organization_id=context.organization_id,
        settings=settings,
        business_date=date(2026, 8, 18),
        reason="Tenant closure",
    )
    return settings, hour, closure


def product_records(context, *, suffix: str, default_available: bool):
    category = Category(
        organization_id=context.organization_id,
        slug="coffee",
        name=f"Coffee {suffix}",
        is_published=True,
    )
    product = Product(
        organization_id=context.organization_id,
        category=category,
        slug="latte",
        name=f"Latte {suffix}",
        base_price_cents=500,
        is_published=True,
    )
    availability = ProductAvailability(
        organization_id=context.organization_id,
        product=product,
        default_available=default_available,
    )
    override = ProductAvailabilityOverride(
        organization_id=context.organization_id,
        product=product,
        business_date=date(2026, 8, 19),
        is_available=not default_available,
    )
    return category, product, availability, override


@pytest.mark.postgresql
def test_hours_closures_and_scheduling_preferences_are_tenant_isolated(
    tenant_availability_engine: Engine,
) -> None:
    with Session(tenant_availability_engine) as session:
        tenant_a, tenant_b = tenant_contexts(session)
        records_a = scheduling_records(tenant_a, lead_time=15, closed=False)
        records_b = scheduling_records(tenant_b, lead_time=90, closed=True)
        session.add_all([*records_a, *records_b])
        session.commit()

        repository_a = AvailabilityRepository(session, tenant_a)
        repository_b = AvailabilityRepository(session, tenant_b)
        assert repository_a.list_business_hours() == [records_a[1]]
        assert repository_b.list_business_hours() == [records_b[1]]
        assert repository_a.list_business_closures() == [records_a[2]]
        assert repository_b.list_business_closures() == [records_b[2]]
        assert repository_a.get_business_closure_by_id(records_b[2].id) is None

        now = datetime(2026, 8, 17, 9, tzinfo=timezone.utc)
        options_a = PickupSchedulingService(repository_a).options(now=now)
        options_b = PickupSchedulingService(repository_b).options(now=now)
        assert options_a.minimum_lead_time_minutes == 15
        assert options_b.minimum_lead_time_minutes == 90
        assert options_a.ordering_available is True
        assert options_b.ordering_available is False

        with pytest.raises(LookupError, match="Closure was not found"):
            save_closure(
                ClosureWrite(business_date=date(2026, 8, 20), reason="Changed"),
                repository_a,
                closure_id=records_b[2].id,
            )
        session.refresh(records_b[2])
        assert records_b[2].business_date == date(2026, 8, 18)


@pytest.mark.postgresql
def test_product_availability_and_public_sellability_are_tenant_isolated(
    tenant_availability_engine: Engine,
) -> None:
    with Session(tenant_availability_engine) as session:
        tenant_a, tenant_b = tenant_contexts(session)
        session.add_all(
            [
                *scheduling_records(tenant_a, lead_time=15, closed=False),
                *scheduling_records(tenant_b, lead_time=15, closed=False),
                *product_records(tenant_a, suffix="A", default_available=True),
                *product_records(tenant_b, suffix="B", default_available=False),
            ]
        )
        session.commit()
        products = session.scalars(select(Product).order_by(Product.id)).all()
        product_a, product_b = products

        repository_a = AvailabilityRepository(session, tenant_a)
        repository_b = AvailabilityRepository(session, tenant_b)
        assert repository_a.get_product_availability(product_b.id) is None
        assert repository_b.get_product_availability(product_a.id) is None

        at = datetime(2026, 8, 19, 12, tzinfo=timezone.utc)
        assert SellabilityService(repository_a).evaluate(product_a.id, at=at).is_sellable is False
        assert SellabilityService(repository_b).evaluate(product_b.id, at=at).is_sellable is True
        assert SellabilityService(repository_a).evaluate(product_b.id, at=at).reason == "Product not found."


@pytest.mark.postgresql
def test_availability_repository_writes_and_cross_tenant_references_fail_closed(
    tenant_availability_engine: Engine,
) -> None:
    with Session(tenant_availability_engine) as session:
        tenant_a, tenant_b = tenant_contexts(session)
        records_a = scheduling_records(tenant_a, lead_time=15, closed=False)
        records_b = scheduling_records(tenant_b, lead_time=15, closed=False)
        product_b_records = product_records(tenant_b, suffix="B", default_available=True)
        session.add_all([*records_a, *records_b, *product_b_records])
        session.commit()

        repository_a = AvailabilityRepository(session, tenant_a)
        with pytest.raises(ValueError, match="another organization"):
            repository_a.add(
                BusinessClosure(
                    organization_id=tenant_b.organization_id,
                    business_settings_id=records_b[0].id,
                    business_date=date(2026, 9, 1),
                )
            )

        with pytest.raises(IntegrityError):
            with tenant_availability_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO business_hours "
                        "(organization_id, business_settings_id, weekday, is_closed) "
                        "VALUES (:tenant_a, :settings_b, 1, true)"
                    ),
                    {
                        "tenant_a": tenant_a.organization_id,
                        "settings_b": records_b[0].id,
                    },
                )

        with pytest.raises(IntegrityError):
            with tenant_availability_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO product_availability_overrides "
                        "(organization_id, product_id, business_date, is_available) "
                        "VALUES (:tenant_a, :product_b, '2026-09-01', true)"
                    ),
                    {
                        "tenant_a": tenant_a.organization_id,
                        "product_b": product_b_records[1].id,
                    },
                )


@pytest.mark.postgresql
def test_same_hours_and_closure_dates_are_valid_for_distinct_tenants(
    tenant_availability_engine: Engine,
) -> None:
    with Session(tenant_availability_engine) as session:
        tenant_a, tenant_b = tenant_contexts(session)
        records_a = scheduling_records(tenant_a, lead_time=15, closed=False)
        records_b = scheduling_records(tenant_b, lead_time=15, closed=False)
        session.add_all([*records_a, *records_b])
        session.commit()
        assert records_a[1].weekday == records_b[1].weekday
        assert records_a[1].opens_at == records_b[1].opens_at
        assert records_a[2].business_date == records_b[2].business_date

        with pytest.raises(IntegrityError):
            with tenant_availability_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO business_closures "
                        "(organization_id, business_settings_id, business_date) "
                        "VALUES (:organization_id, :settings_id, '2026-08-18')"
                    ),
                    {
                        "organization_id": tenant_a.organization_id,
                        "settings_id": records_a[0].id,
                    },
                )
