from uuid import uuid4
from dataclasses import replace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.availability.models import ProductAvailability
from app.catalog.models import Category, Product
from app.catalog.repository import CatalogRepository
from app.catalog.schemas import OwnerCategoryOrderWrite, OwnerCategoryWrite, OwnerProductWrite
from app.catalog.service import CatalogService
from app.jds_auth.models import Organization
from app.platform.models import MediaAsset
from app.platform import starter_media
from app.platform.readiness import evaluate_storefront_readiness
from app.api.v1.platform import archive_media
from app.jds_auth.service import AuthPrincipal
from app.tenancy.resolver import resolve_owner_tenant_context
from tests.test_catalog_api import catalog_api_engine


def service_for(session: Session, organization: Organization) -> CatalogService:
    return CatalogService(CatalogRepository(
        session,
        resolve_owner_tenant_context(session, principal_organization_id=organization.id),
    ), tax_name="HST", tax_rate_millionths=1_300_000)


@pytest.mark.postgresql
def test_category_crud_order_and_safe_delete(catalog_api_engine: Engine) -> None:
    with Session(catalog_api_engine) as session:
        organization = Organization(id=uuid4(), slug=f"category-{uuid4().hex[:8]}", name="Category Test")
        session.add(organization); session.commit()
        service = service_for(session, organization)

        coffee = service.create_category(OwnerCategoryWrite(name="Coffee"))
        duplicate = service.create_category(OwnerCategoryWrite(name="Coffee"))
        bakery = service.create_category(OwnerCategoryWrite(name="Bakery"))
        assert (coffee.slug, duplicate.slug, bakery.slug) == ("coffee", "coffee-2", "bakery")

        renamed = service.update_category(int(coffee.id), OwnerCategoryWrite(name="Hot Drinks", published=False))
        assert renamed.name == "Hot Drinks" and renamed.slug == "coffee" and not renamed.published
        ordered = service.reorder_categories(OwnerCategoryOrderWrite(
            category_ids=[int(bakery.id), int(coffee.id), int(duplicate.id)]
        ))
        assert [item.name for item in ordered] == ["Bakery", "Hot Drinks", "Coffee"]

        service.delete_category(int(duplicate.id))
        assert service._repository.get_category(int(duplicate.id)) is None

        product = Product(
            organization_id=organization.id, category_id=int(coffee.id), slug="latte",
            name="Latte", base_price_cents=475, is_published=True,
        )
        session.add(product); session.commit()
        with pytest.raises(ValueError, match="products or order history"):
            service.delete_category(int(coffee.id))


@pytest.mark.postgresql
def test_catalog_readiness_and_public_projection_use_orderable_category_product(catalog_api_engine: Engine) -> None:
    with Session(catalog_api_engine) as session:
        organization = Organization(id=uuid4(), slug=f"ready-{uuid4().hex[:8]}", name="Ready Test")
        session.add(organization); session.commit()
        service = service_for(session, organization)
        category = service.create_category(OwnerCategoryWrite(name="Coffee"))
        assert not evaluate_storefront_readiness(session, organization.id).checks["catalog"]

        product = service.create_product(OwnerProductWrite(
            slug="latte", name="Latte", description="Espresso and milk",
            base_price_cents=475, category_id=int(category.id), available=True,
            published=True,
        ))
        public = service.build_catalog()
        assert [(item.name, [product.name for product in item.products]) for item in public.categories] == [("Coffee", ["Latte"])]
        assert evaluate_storefront_readiness(session, organization.id).checks["catalog"]

        service.set_product_availability(int(product.id), False)
        assert not evaluate_storefront_readiness(session, organization.id).checks["catalog"]
        service.set_product_availability(int(product.id), True)
        service.update_category(int(category.id), OwnerCategoryWrite(name="Coffee", published=False))
        assert not service.build_catalog().categories
        assert not evaluate_storefront_readiness(session, organization.id).checks["catalog"]


@pytest.mark.postgresql
def test_product_media_assignment_is_tenant_scoped_replaceable_unassignable_and_reusable(catalog_api_engine: Engine, tmp_path, monkeypatch) -> None:
    with Session(catalog_api_engine) as session:
        left = Organization(id=uuid4(), slug=f"media-left-{uuid4().hex[:6]}", name="Left")
        right = Organization(id=uuid4(), slug=f"media-right-{uuid4().hex[:6]}", name="Right")
        session.add_all([left, right]); session.flush()
        category = Category(organization_id=left.id, slug="coffee", name="Coffee", is_published=True)
        foreign = MediaAsset(organization_id=right.id, storage_key="foreign.webp", media_type="image/webp", byte_size=100, checksum="0" * 64)
        own = MediaAsset(organization_id=left.id, storage_key="own.webp", media_type="image/webp", byte_size=100, checksum="1" * 64)
        session.add_all([category, foreign, own]); session.commit()
        service = service_for(session, left)
        base = dict(slug="latte", name="Latte", base_price_cents=475, category_id=category.id)

        monkeypatch.setenv("JDS_STARTER_MEDIA_ROOT", str(tmp_path))
        starter_path = tmp_path / "cafe-restaurant" / "latte-v1.webp"
        starter_path.parent.mkdir(parents=True)
        starter_path.write_bytes(b"reviewed-starter-binary-placeholder")

        with pytest.raises(ValueError, match="this business"):
            service.create_product(OwnerProductWrite(**base, image=f"/api/v1/storefront/media/{foreign.id}"))
        saved = service.create_product(OwnerProductWrite(**base, image=f"/api/v1/storefront/media/{own.id}"))
        assert saved.image.endswith(str(own.id))
        stored = session.get(Product, int(saved.id))
        assert stored.media_asset_id == own.id and not stored.image_reference
        tenant = resolve_owner_tenant_context(session, principal_organization_id=left.id)
        principal = AuthPrincipal(user_id=uuid4(),membership_id=uuid4(),organization_id=left.id,application_id=uuid4(),session_id=uuid4(),email="owner@example.test",display_name="Owner",role="owner",permissions=frozenset(),assurance_level="password")
        with pytest.raises(HTTPException) as referenced:
            archive_media(own.id, principal, tenant, session)
        assert referenced.value.status_code == 409
        service.update_product(int(saved.id), OwnerProductWrite(**base, image=""))
        assert session.get(Product, int(saved.id)).media_asset_id is None
        service.update_product(int(saved.id), OwnerProductWrite(**base, image=f"/api/v1/storefront/media/{own.id}"))
        assert session.get(Product, int(saved.id)).media_asset_id == own.id
        starter_reference = "starter:cafe-restaurant/latte@1"
        service.update_product(int(saved.id), OwnerProductWrite(**base, image=starter_reference))
        assert service.build_owner_catalog().products[0].image == starter_reference
        assert service.build_catalog().categories[0].products[0].image == "/api/v1/storefront/starter-media/cafe-restaurant/latte?version=1"
        right_category = Category(organization_id=right.id, slug="coffee", name="Coffee", is_published=True)
        session.add(right_category); session.commit()
        right_service = service_for(session, right)
        right_service.create_product(OwnerProductWrite(slug="latte", name="Latte", base_price_cents=475, category_id=right_category.id, image=starter_reference))
        assert {item.id for item in session.scalars(select(MediaAsset)).all()} == {foreign.id, own.id}
        monkeypatch.setitem(starter_media.STARTER_MEDIA_BY_REFERENCE, starter_reference, replace(starter_media.starter_asset(starter_reference), active=False))
        service.update_product(int(saved.id), OwnerProductWrite(**base, image=starter_reference, description="Existing retired reference remains valid"))
        with pytest.raises(ValueError, match="no longer available"):
            service.create_product(OwnerProductWrite(slug="second-latte", name="Second Latte", base_price_cents=475, category_id=category.id, image=starter_reference))
        with pytest.raises(ValueError, match="valid JDS starter"):
            service.update_product(int(saved.id), OwnerProductWrite(**base, image="starter:cafe-restaurant/unknown@1"))
        with pytest.raises(ValueError, match="this business"):
            service.update_product(int(saved.id), OwnerProductWrite(**base, image="https://example.test/untrusted.jpg"))
        session.delete(foreign); session.delete(own); session.commit()
