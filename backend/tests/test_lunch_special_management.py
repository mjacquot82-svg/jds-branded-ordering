from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.owner_auth import csrf_principal, current_principal, get_auth_service, get_auth_settings
from app.catalog.models import Category, Product
from app.availability.models import ProductAvailability
from app.jds_auth.foundation import ROLE_PERMISSIONS
from app.jds_auth.models import Organization
from tests.test_owner_orders import owner_orders_api, principal


def catalog_products(engine):
    with Session(engine) as session:
        return list(session.scalars(select(Product).order_by(Product.id)).all())


def ladels_principal(engine, *permissions: str):
    with Session(engine) as session:
        organization_id = session.scalar(
            select(Organization.id).where(Organization.slug == "the-guest-house")
        )
    assert organization_id is not None
    return principal(*permissions, organization_id=organization_id)


def seed_required_products(engine) -> None:
    """Own the two-product precondition instead of relying on another fixture's seed."""
    with Session(engine) as session:
        products = list(session.scalars(select(Product).order_by(Product.id)).all())
        if len(products) >= 2:
            return
        category = session.scalar(select(Category).order_by(Category.id))
        assert category is not None
        second = Product(
            organization_id=category.organization_id,
            category_id=category.id,
            slug="test-lunch-special",
            name="Test Lunch Special",
            description="Deterministic Lunch Special fixture product.",
            base_price_cents=1295,
            image_reference="",
            is_published=True,
            is_featured=False,
            is_lunch_special=False,
            sort_order=999,
            availability=ProductAvailability(default_available=True),
        )
        session.add(second)
        session.commit()


@pytest.mark.postgresql
def test_staff_narrow_operation_selects_replaces_clears_and_feeds_communications(owner_orders_api):
    client, engine = owner_orders_api
    staff = replace(ladels_principal(engine, "catalog.read", "lunch_special.manage", "communications.announce"), role="staff")
    client.app.dependency_overrides[current_principal] = lambda: staff
    client.app.dependency_overrides[csrf_principal] = lambda: staff
    seed_required_products(engine)
    products = catalog_products(engine)
    first, second = products[:2]

    selected = client.put("/api/v1/owner/catalog/lunch-special", json={"product_id": first.id})
    assert selected.status_code == 200
    assert selected.json()["lunch_special"] is True
    with Session(engine) as session:
        assert session.scalars(select(Product).where(Product.is_lunch_special.is_(True))).all() == [session.get(Product, first.id)]

    with Session(engine) as session:
        availability = session.scalar(select(ProductAvailability).where(ProductAvailability.product_id == second.id))
        assert availability is not None
        availability.default_available = False
        session.commit()
    replaced = client.put("/api/v1/owner/catalog/lunch-special", json={"product_id": second.id})
    assert replaced.status_code == 200
    communications = client.get("/api/v1/owner/communications")
    assert communications.status_code == 200
    assert communications.json()["lunch_special"]["id"] == str(second.id)
    assert communications.json()["lunch_special"]["warnings"] == [
        "This Lunch Special is unavailable for online ordering."
    ]
    with Session(engine) as session:
        selected_ids = list(session.scalars(select(Product.id).where(Product.is_lunch_special.is_(True))))
        assert selected_ids == [second.id]

    cleared = client.put("/api/v1/owner/catalog/lunch-special", json={"product_id": None})
    assert cleared.status_code == 200
    assert cleared.json() is None
    with Session(engine) as session:
        assert session.scalar(select(Product.id).where(Product.is_lunch_special.is_(True))) is None


@pytest.mark.postgresql
def test_lunch_special_operation_rejects_extra_fields_hidden_products_and_missing_permission(owner_orders_api):
    client, engine = owner_orders_api
    seed_required_products(engine)
    products = catalog_products(engine)
    target = products[0]
    staff = replace(ladels_principal(engine, "lunch_special.manage"), role="staff")
    client.app.dependency_overrides[csrf_principal] = lambda: staff

    arbitrary = client.put("/api/v1/owner/catalog/lunch-special", json={"product_id": target.id, "name": "Tampered", "base_price_cents": 1})
    assert arbitrary.status_code == 422
    with Session(engine) as session:
        persisted = session.get(Product, target.id)
        assert persisted.name != "Tampered"
        persisted.is_published = False
        session.commit()
    assert client.put("/api/v1/owner/catalog/lunch-special", json={"product_id": target.id}).status_code == 409
    with Session(engine) as session:
        persisted = session.get(Product, target.id)
        persisted.is_published = True
        category = session.get(Category, persisted.category_id)
        assert category is not None
        category.is_published = False
        session.commit()
    assert client.put("/api/v1/owner/catalog/lunch-special", json={"product_id": target.id}).status_code == 409

    denied = replace(ladels_principal(engine), role="staff")
    client.app.dependency_overrides[csrf_principal] = lambda: denied
    assert client.put("/api/v1/owner/catalog/lunch-special", json={"product_id": products[1].id}).status_code == 403


@pytest.mark.postgresql
def test_staff_remains_denied_broad_catalog_edit_while_owner_retains_it(owner_orders_api):
    client, engine = owner_orders_api
    product = catalog_products(engine)[0]
    with Session(engine) as auth_session:
        organization = auth_session.scalar(
            select(Organization).where(Organization.slug == "the-guest-house")
        )
        if organization is None:
            organization = Organization(slug="the-guest-house", name="The Guest House")
            auth_session.add(organization)
            auth_session.commit()
        organization_id = organization.id
        client.app.dependency_overrides[get_auth_service] = lambda: SimpleNamespace(_session=auth_session)
        client.app.dependency_overrides[get_auth_settings] = lambda: SimpleNamespace(organization_slug="the-guest-house")

        staff = replace(
            ladels_principal(engine, "catalog.read", "availability.manage", "lunch_special.manage"),
            organization_id=organization_id,
            role="staff",
        )
        client.app.dependency_overrides[csrf_principal] = lambda: staff
        broad_payload = {
            "slug": product.slug, "name": "Forbidden rename", "description": product.description or "",
            "base_price_cents": product.base_price_cents, "category_id": product.category_id,
            "image": product.image_reference or "", "available": True, "featured": product.is_featured,
            "lunch_special": False, "published": product.is_published, "sort_order": product.sort_order,
            "variants": [], "modifier_group_ids": [],
        }
        assert client.put(f"/api/v1/owner/catalog/products/{product.id}", json=broad_payload).status_code == 403

        owner = replace(
            ladels_principal(engine, "catalog.write", "catalog.publish", "availability.manage", "modifiers.manage", "lunch_special.manage"),
            organization_id=organization_id,
        )
        client.app.dependency_overrides[csrf_principal] = lambda: owner
        assert client.put(f"/api/v1/owner/catalog/products/{product.id}", json=broad_payload).status_code == 200


def test_final_staff_lunch_special_permission_is_narrow():
    permissions = ROLE_PERMISSIONS["staff"]
    assert "lunch_special.manage" in permissions
    assert {"catalog.write", "catalog.publish", "modifiers.manage", "members.manage", "integrations.manage"}.isdisjoint(permissions)
