from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.availability.models import BusinessSettings
from app.availability.repository import AvailabilityRepository
from app.catalog.models import Category, ModifierGroup, Product, ProductModifierGroup
from app.catalog.repository import CatalogRepository
from app.catalog.service import CatalogService
from app.jds_auth.models import Organization
from app.tenancy.context import TenantResolutionSource
from app.tenancy.resolver import (
    LADELS_ORGANIZATION_SLUG,
    TenantResolutionError,
    resolve_ladels_compatibility_context,
    resolve_owner_tenant_context,
)
from tests.test_migrations import make_alembic_config


@pytest.fixture
def tenant_catalog_engine(postgresql_url: str) -> Iterator[Engine]:
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE product_modifier_groups, modifier_options, product_variants, "
                "product_availability_overrides, product_availability, products, "
                "modifier_groups, categories, business_closures, business_hours, "
                "business_settings RESTART IDENTITY CASCADE"
            )
        )
        connection.execute(
            text("DELETE FROM organizations WHERE slug = 'tenant-b'")
        )
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE product_modifier_groups, modifier_options, product_variants, "
                    "product_availability_overrides, product_availability, products, "
                    "modifier_groups, categories, business_closures, business_hours, "
                    "business_settings RESTART IDENTITY CASCADE"
                )
            )
            connection.execute(text("DELETE FROM organizations WHERE slug = 'tenant-b'"))
        engine.dispose()


def _contexts(session: Session):
    ladels = session.scalar(
        select(Organization).where(Organization.slug == LADELS_ORGANIZATION_SLUG)
    )
    tenant_b = Organization(id=uuid4(), slug="tenant-b", name="Tenant B")
    session.add(tenant_b)
    session.flush()
    return (
        resolve_owner_tenant_context(
            session, principal_organization_id=ladels.id
        ),
        resolve_owner_tenant_context(
            session, principal_organization_id=tenant_b.id
        ),
    )


def _root_records(context, *, suffix: str = ""):
    category = Category(
        organization_id=context.organization_id,
        slug="coffee",
        name=f"Coffee{suffix}",
        is_published=True,
        sort_order=0,
    )
    group = ModifierGroup(
        organization_id=context.organization_id,
        key="milk",
        name=f"Milk{suffix}",
        selection_type="single",
        is_required=False,
        minimum_selections=0,
        maximum_selections=1,
        sort_order=0,
    )
    product = Product(
        organization_id=context.organization_id,
        category=category,
        slug="latte",
        name=f"Latte{suffix}",
        base_price_cents=500,
        is_published=True,
        is_lunch_special=False,
        sort_order=0,
    )
    settings = BusinessSettings(
        organization_id=context.organization_id,
        timezone="America/Toronto",
        minimum_lead_time_minutes=15,
        pickup_interval_minutes=5,
        maximum_advance_days=14,
    )
    return category, group, product, settings


def test_tenant_context_is_immutable() -> None:
    # A context is issued by a trusted resolver and cannot be re-scoped in place.
    from app.tenancy.context import TenantContext

    context = TenantContext(
        organization_id=uuid4(),
        organization_slug="immutable",
        source=TenantResolutionSource.AUTHENTICATED_MEMBERSHIP,
    )
    with pytest.raises(FrozenInstanceError):
        context.organization_slug = "changed"


@pytest.mark.postgresql
def test_compatibility_resolution_fails_closed_for_unknown_or_conflicting_context(
    tenant_catalog_engine: Engine,
) -> None:
    with Session(tenant_catalog_engine) as session:
        context = resolve_ladels_compatibility_context(session, host="test")
        assert context.organization_slug == LADELS_ORGANIZATION_SLUG

        with pytest.raises(TenantResolutionError, match="not a known"):
            resolve_ladels_compatibility_context(session, host="unknown.example")
        with pytest.raises(TenantResolutionError, match="Client-supplied"):
            resolve_ladels_compatibility_context(
                session,
                host="test",
                headers={"x-tenant-id": str(uuid4())},
            )
        with pytest.raises(TenantResolutionError, match="Client-supplied"):
            resolve_ladels_compatibility_context(
                session,
                host="test",
                query_params={"organization_id": str(uuid4())},
            )


@pytest.mark.postgresql
def test_catalog_reads_and_mutations_are_isolated_by_tenant(
    tenant_catalog_engine: Engine,
) -> None:
    with Session(tenant_catalog_engine) as session:
        tenant_a, tenant_b = _contexts(session)
        roots_a = _root_records(tenant_a, suffix=" A")
        roots_b = _root_records(tenant_b, suffix=" B")
        session.add_all([*roots_a, *roots_b])
        session.commit()

        category_a, group_a, product_a, _ = roots_a
        category_b, group_b, product_b, _ = roots_b
        repository_a = CatalogRepository(session, tenant_a)

        assert repository_a.list_categories() == [category_a]
        assert repository_a.list_products() == [product_a]
        assert repository_a.list_modifier_groups() == [group_a]
        assert repository_a.get_category(category_b.id) is None
        assert repository_a.get_product(product_b.id) is None
        assert repository_a.get_modifier_group(group_b.id) is None

        with pytest.raises(LookupError, match="Product not found"):
            CatalogService(repository_a).archive_product(product_b.id)
        with pytest.raises(ValueError, match="another organization"):
            repository_a.replace_modifier_assignments(product_a.id, [group_b.id])

        session.refresh(product_b)
        assert product_b.archived_at is None


@pytest.mark.postgresql
def test_tenant_unique_keys_and_associations_are_database_enforced(
    tenant_catalog_engine: Engine,
) -> None:
    with Session(tenant_catalog_engine) as session:
        tenant_a, tenant_b = _contexts(session)
        roots_a = _root_records(tenant_a, suffix=" A")
        roots_b = _root_records(tenant_b, suffix=" B")
        session.add_all([*roots_a, *roots_b])
        session.commit()

        category_a, group_a, product_a, _ = roots_a
        category_b, group_b, _, _ = roots_b
        # Identical category/product slugs and modifier keys coexist across tenants.
        assert category_a.slug == category_b.slug
        assert group_a.key == group_b.key

        with pytest.raises(IntegrityError):
            with tenant_catalog_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO categories (organization_id, slug, name) "
                        "VALUES (:organization_id, 'coffee', 'Duplicate')"
                    ),
                    {"organization_id": tenant_a.organization_id},
                )

        with pytest.raises(IntegrityError):
            with tenant_catalog_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO products "
                        "(organization_id, category_id, slug, name, base_price_cents) "
                        "VALUES (:organization_id, :category_id, 'cross-category', "
                        "'Cross category', 100)"
                    ),
                    {
                        "organization_id": tenant_a.organization_id,
                        "category_id": category_b.id,
                    },
                )

        with pytest.raises(IntegrityError):
            with tenant_catalog_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO product_modifier_groups "
                        "(product_id, modifier_group_id) VALUES (:product_id, :group_id)"
                    ),
                    {"product_id": product_a.id, "group_id": group_b.id},
                )


@pytest.mark.postgresql
def test_lunch_special_settings_and_lock_keys_are_tenant_scoped(
    tenant_catalog_engine: Engine,
) -> None:
    with Session(tenant_catalog_engine) as session:
        tenant_a, tenant_b = _contexts(session)
        roots_a = _root_records(tenant_a, suffix=" A")
        roots_b = _root_records(tenant_b, suffix=" B")
        roots_a[2].is_lunch_special = True
        roots_b[2].is_lunch_special = True
        roots_a[3].minimum_lead_time_minutes = 15
        roots_b[3].minimum_lead_time_minutes = 45
        session.add_all([*roots_a, *roots_b])
        session.commit()

        repository_a = CatalogRepository(session, tenant_a)
        repository_b = CatalogRepository(session, tenant_b)
        assert repository_a.lunch_special_lock_key != repository_b.lunch_special_lock_key

        repository_a.clear_lunch_special()
        session.commit()
        session.refresh(roots_a[2])
        session.refresh(roots_b[2])
        assert roots_a[2].is_lunch_special is False
        assert roots_b[2].is_lunch_special is True

        settings_a = AvailabilityRepository(session, tenant_a).get_business_settings()
        settings_b = AvailabilityRepository(session, tenant_b).get_business_settings()
        assert settings_a.minimum_lead_time_minutes == 15
        assert settings_b.minimum_lead_time_minutes == 45
        settings_a.minimum_lead_time_minutes = 20
        session.commit()
        session.refresh(settings_b)
        assert settings_b.minimum_lead_time_minutes == 45
