"""M3 starter image library: select/replace/remove, starter vs upload, isolation, quota."""
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.v1.platform import archive_media
from app.catalog.models import Category, Product
from app.catalog.schemas import OwnerProductWrite
from app.jds_auth.models import JdsUser, Organization
from app.jds_auth.service import AuthPrincipal
from app.platform.demo_limits import DEMO_MAX_MEDIA_FILES
from app.platform.demo_service import enforce_demo_media_limits
from app.platform.models import DesignWorkspace, MediaAsset
from app.tenancy.resolver import resolve_owner_tenant_context
from tests.test_catalog_api import catalog_api_engine  # noqa: F401
from tests.test_owner_category_management import service_for

LATTE = "starter:cafe-restaurant/latte@1"
MUFFIN = "starter:cafe-restaurant/muffin@1"


@pytest.fixture(autouse=True)
def shipped_pack(monkeypatch):
    monkeypatch.delenv("JDS_STARTER_MEDIA_ROOT", raising=False)


def _org(session: Session, name: str, mode: str = "prospect") -> Organization:
    organization = Organization(id=uuid4(), slug=f"m3-{uuid4().hex[:8]}", name=name, commercial_mode=mode)
    session.add(organization); session.flush()
    return organization


def _media(session: Session, organization: Organization, name: str) -> MediaAsset:
    item = MediaAsset(organization_id=organization.id, storage_key=f"{organization.id}/{name}.webp", media_type="image/webp", purpose="product", byte_size=1000, width=900, height=900, checksum=uuid4().hex + uuid4().hex)
    session.add(item); session.flush()
    return item


def _principal(session: Session, organization: Organization) -> AuthPrincipal:
    user = JdsUser(primary_email=f"owner-{uuid4().hex[:10]}@example.test", display_name="Owner")
    session.add(user); session.commit()
    return AuthPrincipal(user_id=user.id, membership_id=uuid4(), organization_id=organization.id, application_id=uuid4(), session_id=uuid4(), email="owner@example.test", display_name="Owner", role="owner", permissions=frozenset(), assurance_level="password")


def _active_media(session: Session, organization: Organization) -> int:
    return session.scalar(select(func.count()).select_from(MediaAsset).where(MediaAsset.organization_id == organization.id, MediaAsset.status == "active"))


@pytest.mark.postgresql
def test_starter_select_replace_upload_remove_round_trip_and_sources(catalog_api_engine: Engine) -> None:
    with Session(catalog_api_engine) as session:
        org = _org(session, "Round Trip Café")
        category = Category(organization_id=org.id, slug="coffee", name="Coffee", is_published=True)
        session.add(category); session.commit()
        upload = _media(session, org, "latte-photo"); session.commit()
        service = service_for(session, org)
        base = dict(slug="latte", name="Latte", base_price_cents=495, category_id=category.id)

        saved = service.create_product(OwnerProductWrite(**base, image=LATTE))
        pid = int(saved.id)
        assert saved.image == LATTE and saved.image_source == "starter"
        assert _active_media(session, org) == 1  # starter selection created no media row

        replaced = service.update_product(pid, OwnerProductWrite(**base, image=MUFFIN))
        assert replaced.image == MUFFIN and replaced.image_source == "starter"

        with_upload = service.update_product(pid, OwnerProductWrite(**base, image=f"/api/v1/storefront/media/{upload.id}"))
        stored = session.get(Product, pid)
        assert with_upload.image_source == "upload" and stored.media_asset_id == upload.id and not stored.image_reference

        back_to_starter = service.update_product(pid, OwnerProductWrite(**base, image=LATTE))
        stored = session.get(Product, pid)
        assert back_to_starter.image_source == "starter" and stored.media_asset_id is None and stored.image_reference == LATTE

        removed = service.update_product(pid, OwnerProductWrite(**base, image=""))
        stored = session.get(Product, pid)
        assert removed.image_source == "none" and stored.media_asset_id is None and not stored.image_reference

        service.update_product(pid, OwnerProductWrite(**base, image=MUFFIN))
        session.expire_all()
        # Persistence: a fresh read (as after sign-out/sign-in) sees the same selection.
        fresh = service_for(session, org).build_owner_catalog().products[0]
        assert fresh.image == MUFFIN and fresh.image_source == "starter"
        public = service_for(session, org).build_catalog().categories[0].products[0]
        assert public.image == "/api/v1/storefront/starter-media/cafe-restaurant/muffin?version=1"


@pytest.mark.postgresql
def test_malformed_unavailable_and_external_references_are_rejected(catalog_api_engine: Engine) -> None:
    with Session(catalog_api_engine) as session:
        org = _org(session, "Validation Café")
        category = Category(organization_id=org.id, slug="coffee", name="Coffee", is_published=True)
        session.add(category); session.commit()
        service = service_for(session, org)
        base = dict(slug="latte", name="Latte", base_price_cents=495, category_id=category.id)
        for bad in (
            "starter:cafe-restaurant/../../etc/passwd@1",
            "starter:cafe-restaurant/latte@abc",
            "starter:other/latte@1",
            "starter:cafe-restaurant/not-real@1",
            "https://images.example.test/latte.jpg",
            "//cdn.example.test/x.png",
            "/api/v1/storefront/media/not-a-uuid",
        ):
            with pytest.raises(ValueError):
                service.create_product(OwnerProductWrite(**base, image=bad))
        # A manifest archetype without shipped art cannot be newly selected.
        with pytest.raises(ValueError, match="no longer available|not available|valid JDS starter"):
            service.create_product(OwnerProductWrite(**base, image="starter:cafe-restaurant/americano@1"))
        assert session.scalar(select(func.count()).select_from(Product).where(Product.organization_id == org.id)) == 0


@pytest.mark.postgresql
def test_starters_are_shared_but_uploads_are_tenant_isolated(catalog_api_engine: Engine) -> None:
    with Session(catalog_api_engine) as session:
        left, right = _org(session, "Left Café"), _org(session, "Right Café")
        lc = Category(organization_id=left.id, slug="coffee", name="Coffee", is_published=True)
        rc = Category(organization_id=right.id, slug="coffee", name="Coffee", is_published=True)
        session.add_all([lc, rc]); session.commit()
        left_upload = _media(session, left, "left-photo"); session.commit()
        left_service, right_service = service_for(session, left), service_for(session, right)
        left_service.create_product(OwnerProductWrite(slug="latte", name="Latte", base_price_cents=495, category_id=lc.id, image=LATTE))
        right_service.create_product(OwnerProductWrite(slug="latte", name="Latte", base_price_cents=495, category_id=rc.id, image=LATTE))
        with pytest.raises(ValueError, match="this business"):
            right_service.create_product(OwnerProductWrite(slug="stolen", name="Stolen", base_price_cents=100, category_id=rc.id, image=f"/api/v1/storefront/media/{left_upload.id}"))
        right_tenant = resolve_owner_tenant_context(session, principal_organization_id=right.id)
        with pytest.raises(HTTPException) as foreign_archive:
            archive_media(left_upload.id, _principal(session, right), right_tenant, session)
        assert foreign_archive.value.status_code == 404
        assert session.get(MediaAsset, left_upload.id).status == "active"
        assert _active_media(session, right) == 0


@pytest.mark.postgresql
def test_unused_upload_can_be_deleted_to_free_prospect_quota_but_in_use_media_is_protected(catalog_api_engine: Engine) -> None:
    with Session(catalog_api_engine) as session:
        org = _org(session, "Quota Café")
        category = Category(organization_id=org.id, slug="coffee", name="Coffee", is_published=True)
        session.add(category); session.commit()
        service = service_for(session, org)
        tenant = resolve_owner_tenant_context(session, principal_organization_id=org.id)
        principal = _principal(session, org)
        uploads = [_media(session, org, f"photo-{index}") for index in range(DEMO_MAX_MEDIA_FILES)]
        session.commit()
        with pytest.raises(HTTPException) as full:
            enforce_demo_media_limits(session, org.id, incoming_bytes=1000)
        assert full.value.status_code in {403, 409, 413, 422, 429}

        first = uploads[0]
        saved = service.create_product(OwnerProductWrite(slug="latte", name="Latte", base_price_cents=495, category_id=category.id, image=f"/api/v1/storefront/media/{first.id}"))
        with pytest.raises(HTTPException) as used:
            archive_media(first.id, principal, tenant, session)
        assert used.value.status_code == 409

        # Replace the upload with a starter: upload still counts until the owner deletes it.
        service.update_product(int(saved.id), OwnerProductWrite(slug="latte", name="Latte", base_price_cents=495, category_id=category.id, image=LATTE))
        assert _active_media(session, org) == DEMO_MAX_MEDIA_FILES
        archive_media(first.id, principal, tenant, session)
        assert session.get(MediaAsset, first.id).status == "archived"
        enforce_demo_media_limits(session, org.id, incoming_bytes=1000)  # room again

        # Media referenced by the unpublished design draft is protected too.
        draft_logo = uploads[1]
        session.add(DesignWorkspace(organization_id=org.id, draft_config={"logo": {"mediaId": str(draft_logo.id)}}))
        session.commit()
        with pytest.raises(HTTPException) as in_draft:
            archive_media(draft_logo.id, principal, tenant, session)
        assert in_draft.value.status_code == 409
        assert session.get(MediaAsset, draft_logo.id).status == "active"


@pytest.mark.postgresql
def test_legacy_image_tokens_remain_readable(catalog_api_engine: Engine) -> None:
    with Session(catalog_api_engine) as session:
        org = _org(session, "Legacy Café", mode="live")
        category = Category(organization_id=org.id, slug="coffee", name="Coffee", is_published=True)
        session.add(category); session.flush()
        session.add(Product(organization_id=org.id, category_id=category.id, slug="old", name="Old", base_price_cents=100, is_published=True, image_reference="/product-images/croissant.jpg"))
        session.commit()
        owner = service_for(session, org).build_owner_catalog().products[0]
        assert owner.image == "/product-images/croissant.jpg" and owner.image_source == "legacy"
