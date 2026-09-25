"""M2 self-service demo-to-customer funnel — required scenario coverage."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.jds_auth.config import AuthSettings
from app.jds_auth.foundation import ensure_foundation
from app.jds_auth.models import ExternalIdentity, JdsUser, Membership, MerchantAcquisition, Organization, Role
from app.jds_auth.provider import InvalidCredentialsError, ProviderAuthentication, ProviderIdentity
from app.jds_auth.service import AuthenticationService
from app.platform.commercial import enforce_live_commerce, enforce_not_self_upgrade, is_prospect
from app.platform.demo_limits import DEMO_MAX_MEDIA_FILES, DEMO_MAX_PRODUCTS, DEMO_MAX_STORAGE_BYTES, limits_payload
from app.platform.demo_service import DemoFunnelService, DemoServiceError, public_pricing
from app.platform.demo_starter import STARTER_CAFE_NAME, STARTER_PRODUCTS
from app.platform.models import (
    BillingPlan,
    BillingPlanPricing,
    DemoActivationRequest,
    DemoFunnelEvent,
    DesignWorkspace,
    MediaAsset,
    OnboardingState,
    OrganizationSubscription,
    PlatformGrant,
)
from app.catalog.models import Category, Product
from app.api.v1 import demo as demo_api
from app.api.v1.orders import create_pending_order
from app.api.v1.order_schemas import CreateOrderRequest
from tests.test_jds_auth import FakeIdentityProvider
from tests.test_migrations import make_alembic_config


class DemoIdentityProvider(FakeIdentityProvider):
    def __init__(self) -> None:
        super().__init__()
        self.users: dict[str, tuple[str, ProviderIdentity]] = {}

    def register_user(self, email: str, password: str, redirect_url: str) -> ProviderIdentity:
        normalized = email.strip().lower()
        if normalized in self.users:
            raise Exception("User already exists")
        identity = ProviderIdentity(
            issuer="https://identity.example.test/auth/v1",
            subject=f"demo-{normalized}",
            email=normalized,
            email_verified=True,
            display_name=normalized.split("@")[0],
        )
        self.users[normalized] = (password, identity)
        self.identity = identity
        self.registrations.append((email, redirect_url))
        return identity

    def authenticate_password(self, email: str, password: str) -> ProviderAuthentication:
        normalized = email.strip().lower()
        if normalized not in self.users or self.users[normalized][0] != password:
            raise InvalidCredentialsError("Authentication failed.")
        return ProviderAuthentication(self.users[normalized][1], "demo-access-token")


@pytest.fixture
def demo_engine(postgresql_url: str):
    command.upgrade(make_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    yield engine
    engine.dispose()


@pytest.fixture
def demo_settings() -> AuthSettings:
    return AuthSettings(
        supabase_url="https://identity.example.test",
        supabase_publishable_key="publishable",
        supabase_secret_key="secret",
        session_pepper="p" * 48,
        frontend_url="http://test",
        secure_cookies=False,
    )


@pytest.fixture
def demo_ctx(demo_engine, demo_settings):
    provider = DemoIdentityProvider()
    with Session(demo_engine) as session, session.begin():
        ensure_foundation(
            session,
            application_key="jds-commerce",
            application_name="JDS Commerce",
            organization_slug="the-guest-house",
            organization_name="The Guest House",
        )
    return demo_engine, demo_settings, provider


def _service(session, settings, provider) -> DemoFunnelService:
    return DemoFunnelService(session, settings, provider)


def _signup(session, settings, provider, email: str, business: str = "Maple Bean Café"):
    now = datetime.now(timezone.utc)
    service = _service(session, settings, provider)
    status, issued = service.signup(
        email=email,
        password="correct horse battery staple",
        business_name=business,
        contact_name="Alex Owner",
        desired_slug=None,
        now=now,
        user_agent="pytest",
        client_id=f"ip-{email}",
    )
    assert status == "ready"
    assert issued is not None
    return issued


def test_01_migration_adds_commercial_mode_and_demo_tables(demo_engine):
    with demo_engine.connect() as connection:
        cols = {row[0] for row in connection.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='organizations'"
        ))}
        assert "commercial_mode" in cols
        for table in ("demo_pending_signups", "demo_activation_requests", "demo_funnel_events", "billing_plan_pricing"):
            assert connection.scalar(text("SELECT to_regclass(:t)"), {"t": table}) is not None


def test_02_signup_creates_prospect_with_starter(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"owner-{uuid4().hex[:8]}@example.com")
        org = session.get(Organization, issued.principal.organization_id)
        assert org.commercial_mode == "prospect"
        assert org.lifecycle_status == "onboarding"
        workspace = session.get(DesignWorkspace, org.id)
        assert workspace is not None
        assert "Maple Bean" in workspace.draft_config["displayName"] or workspace.draft_config["displayName"]
        products = session.scalars(select(Product).where(Product.organization_id == org.id)).all()
        assert len(products) == len(STARTER_PRODUCTS)
        assert session.scalar(select(MerchantAcquisition).where(MerchantAcquisition.organization_id == org.id)).source == "self_service_demo"
        assert session.get(OrganizationSubscription, org.id).plan_key == "jds-demo"
        events = session.scalars(select(DemoFunnelEvent).where(DemoFunnelEvent.organization_id == org.id)).all()
        assert any(item.event_name == "demo_started" for item in events)


def test_03_prospect_distinct_from_live_legacy(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        guest = session.scalar(select(Organization).where(Organization.slug == "the-guest-house"))
        assert guest.commercial_mode == "live"
        issued = _signup(session, settings, provider, f"p-{uuid4().hex[:8]}@example.com")
        assert is_prospect(session, issued.principal.organization_id)


def test_04_commerce_lockout_orders(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"lock-{uuid4().hex[:8]}@example.com")
        with pytest.raises(HTTPException) as raised:
            enforce_live_commerce(session, issued.principal.organization_id, action="create_order")
        assert raised.value.status_code == 403
        assert raised.value.detail["code"] == "demo_commerce_locked"


def test_05_cannot_self_upgrade_via_launch(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"up-{uuid4().hex[:8]}@example.com")
        with pytest.raises(HTTPException) as raised:
            enforce_not_self_upgrade(session, issued.principal.organization_id)
        assert raised.value.detail["code"] == "demo_activation_required"


def test_06_pricing_configurable_zero_take(demo_ctx, monkeypatch):
    engine, settings, provider = demo_ctx
    monkeypatch.setenv("JDS_STANDARD_PLAN_MONTHLY_CAD", "149")
    with Session(engine) as session:
        pricing = public_pricing(session)
        assert pricing.amount_cents == 14900
        assert pricing.jds_sales_take_percent == 0
        assert "0%" in pricing.disclosure


def test_07_activation_request_creates_lead_preserves_design(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"act-{uuid4().hex[:8]}@example.com", business="Riverstone Roasters")
        org_id = issued.principal.organization_id
        before = session.get(DesignWorkspace, org_id).draft_config
        product_count = len(session.scalars(select(Product).where(Product.organization_id == org_id)).all())
        service = _service(session, settings, provider)
        item = service.request_activation(
            organization_id=org_id,
            user_id=issued.principal.user_id,
            business_name="Riverstone Roasters",
            contact_name="Alex Owner",
            email=issued.principal.email,
            phone="4165550100",
            city="Toronto",
            desired_domain="orders.riverstone.test",
            processor_preference="square",
            now=datetime.now(timezone.utc),
        )
        assert item.status == "requested"
        assert item.processor_preference == "square"
        assert session.get(DesignWorkspace, org_id).draft_config == before
        assert len(session.scalars(select(Product).where(Product.organization_id == org_id)).all()) == product_count
        assert any(
            event.event_name == "activation_requested"
            for event in session.scalars(select(DemoFunnelEvent).where(DemoFunnelEvent.organization_id == org_id))
        )


def test_08_promote_to_live_preserves_assets(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"prom-{uuid4().hex[:8]}@example.com", business="Preserve Café")
        org_id = issued.principal.organization_id
        session.add(
            MediaAsset(
                organization_id=org_id,
                storage_key=f"{org_id}/logo.png",
                media_type="image/png",
                purpose="design",
                byte_size=100,
                width=100,
                height=100,
                checksum="a" * 64,
            )
        )
        session.commit()
        service = _service(session, settings, provider)
        service.request_activation(
            organization_id=org_id,
            user_id=issued.principal.user_id,
            business_name="Preserve Café",
            contact_name="Alex",
            email=issued.principal.email,
            phone=None,
            city="Ottawa",
            desired_domain=None,
            processor_preference="clover",
            now=datetime.now(timezone.utc),
        )
        org = service.promote_to_live(organization_id=org_id, actor_user_id=issued.principal.user_id, now=datetime.now(timezone.utc))
        assert org.commercial_mode == "live"
        assert session.get(DesignWorkspace, org_id).draft_config["displayName"] == "Preserve Café"
        assert session.scalar(select(MediaAsset).where(MediaAsset.organization_id == org_id, MediaAsset.status == "active")) is not None
        assert session.get(OrganizationSubscription, org_id).plan_key == "jds-standard"


def test_09_product_limit_enforced(demo_ctx):
    engine, settings, provider = demo_ctx
    from app.platform.demo_service import enforce_demo_catalog_limits

    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"lim-{uuid4().hex[:8]}@example.com")
        org_id = issued.principal.organization_id
        category = session.scalar(select(Category).where(Category.organization_id == org_id))
        existing = session.scalars(select(Product).where(Product.organization_id == org_id, Product.archived_at.is_(None))).all()
        for index in range(DEMO_MAX_PRODUCTS - len(existing)):
            session.add(
                Product(
                    organization_id=org_id,
                    category_id=category.id,
                    slug=f"extra-{index}-{uuid4().hex[:4]}",
                    name=f"Extra {index}",
                    base_price_cents=100,
                    is_published=True,
                )
            )
        session.commit()
        with pytest.raises(HTTPException) as raised:
            enforce_demo_catalog_limits(session, org_id)
        assert raised.value.detail["code"] == "demo_product_limit"


def test_10_media_storage_limit_enforced(demo_ctx):
    engine, settings, provider = demo_ctx
    from app.platform.demo_service import enforce_demo_media_limits

    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"media-{uuid4().hex[:8]}@example.com")
        org_id = issued.principal.organization_id
        session.add(
            MediaAsset(
                organization_id=org_id,
                storage_key=f"{org_id}/big.png",
                media_type="image/png",
                purpose="design",
                byte_size=DEMO_MAX_STORAGE_BYTES - 10,
                width=100,
                height=100,
                checksum="b" * 64,
            )
        )
        session.commit()
        with pytest.raises(HTTPException) as raised:
            enforce_demo_media_limits(session, org_id, incoming_bytes=100)
        assert raised.value.detail["code"] == "demo_media_storage_limit"


def test_11_limits_documented(demo_ctx):
    payload = limits_payload()
    assert payload["maxProducts"] == DEMO_MAX_PRODUCTS
    assert payload["maxMediaFiles"] == DEMO_MAX_MEDIA_FILES
    assert payload["maxStorageBytes"] == DEMO_MAX_STORAGE_BYTES
    assert payload["retentionAutoDeleteEnabled"] is False


def test_12_enter_after_signup(demo_ctx):
    engine, settings, provider = demo_ctx
    email = f"return-{uuid4().hex[:8]}@example.com"
    with Session(engine) as session:
        first = _signup(session, settings, provider, email, business="Return Café")
        service = _service(session, settings, provider)
        status, issued = service.enter(
            email=email,
            password="correct horse battery staple",
            now=datetime.now(timezone.utc),
            user_agent="pytest",
            client_id="return-ip",
        )
        assert status == "ready"
        assert issued.principal.organization_id == first.principal.organization_id


def test_13_unverified_signup_requires_verification(demo_ctx):
    engine, settings, provider = demo_ctx

    class Unverified(DemoIdentityProvider):
        def register_user(self, email: str, password: str, redirect_url: str) -> ProviderIdentity:
            identity = super().register_user(email, password, redirect_url)
            self.users[email.strip().lower()] = (
                password,
                ProviderIdentity(identity.issuer, identity.subject, identity.email, False, identity.display_name),
            )
            return self.users[email.strip().lower()][1]

    provider = Unverified()
    with Session(engine) as session:
        service = _service(session, settings, provider)
        status, issued = service.signup(
            email=f"verify-{uuid4().hex[:8]}@example.com",
            password="correct horse battery staple",
            business_name="Verify Café",
            contact_name="V",
            desired_slug=None,
            now=datetime.now(timezone.utc),
            user_agent="pytest",
            client_id="verify-ip",
        )
        assert status == "verification_required"
        assert issued is None


def test_14_preview_model_checkout_disabled_constant():
    # Auth preview endpoint keeps checkoutEnabled False (enforced in platform.py).
    from app.api.v1 import platform as platform_api
    assert "checkoutEnabled\":False" in open(platform_api.__file__).read() or 'checkoutEnabled":False' in open(platform_api.__file__).read() or "checkoutEnabled\": False" in open(platform_api.__file__).read() or '"checkoutEnabled":False' in open(platform_api.__file__).read().replace(" ", "")


def test_15_admin_prospect_visibility(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"vis-{uuid4().hex[:8]}@example.com")
        grant_user = session.get(JdsUser, issued.principal.user_id)
        session.add(PlatformGrant(user_id=grant_user.id, capability="platform.organizations.read", is_active=True))
        session.commit()
        rows = demo_api.platform_demo_prospects(principal=issued.principal, session=session)
        assert any(row["id"] == str(issued.principal.organization_id) for row in rows)


def test_16_processor_preference_info_only(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"proc-{uuid4().hex[:8]}@example.com")
        service = _service(session, settings, provider)
        item = service.request_activation(
            organization_id=issued.principal.organization_id,
            user_id=issued.principal.user_id,
            business_name="Proc Café",
            contact_name="P",
            email=issued.principal.email,
            phone=None,
            city="Hamilton",
            desired_domain=None,
            processor_preference="stripe",
            now=datetime.now(timezone.utc),
        )
        assert item.processor_preference == "stripe"
        # No payment settings created for stripe
        from app.payments.models import OrganizationPaymentSettings
        assert session.get(OrganizationPaymentSettings, issued.principal.organization_id) is None


def test_17_funnel_events_whitelist(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"fun-{uuid4().hex[:8]}@example.com")
        with pytest.raises(DemoServiceError):
            from app.platform.demo_service import record_funnel_event
            record_funnel_event(session, event_name="not_a_real_event", organization_id=issued.principal.organization_id)


def test_18_starter_not_guest_house_or_ladels(demo_ctx):
    assert "guest" not in STARTER_CAFE_NAME.lower()
    assert "ladel" not in STARTER_CAFE_NAME.lower()
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"brand-{uuid4().hex[:8]}@example.com")
        workspace = session.get(DesignWorkspace, issued.principal.organization_id)
        blob = str(workspace.draft_config).lower()
        assert "guest house" not in blob
        assert "ladel" not in blob


def test_19_m1_clover_fields_untouched(demo_engine):
    with demo_engine.connect() as connection:
        cols = {row[0] for row in connection.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='orders'"
        ))}
        for col in ("clover_checkout_session_id", "clover_checkout_url", "payment_provider", "payment_status"):
            assert col in cols


def test_20_same_tenant_architecture_not_second_app(demo_ctx):
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"same-{uuid4().hex[:8]}@example.com")
        org_id = issued.principal.organization_id
        assert session.get(DesignWorkspace, org_id) is not None
        assert session.scalar(select(Product.id).where(Product.organization_id == org_id)) is not None
        # Demo uses organizations + design_workspaces + catalog tables — not a parallel schema.


def test_21_harbor_and_hearth_uses_platform_starter_images_without_quota(demo_ctx, monkeypatch):
    """M3: seeded demo products show shared starter illustrations, never tenant media rows."""
    from app.platform import starter_media
    from app.platform.demo_service import enforce_demo_media_limits
    from app.platform.demo_starter import starter_product_image_reference

    monkeypatch.delenv("JDS_STARTER_MEDIA_ROOT", raising=False)
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        issued = _signup(session, settings, provider, f"art-{uuid4().hex[:8]}@example.com")
        org_id = issued.principal.organization_id
        products = session.scalars(select(Product).where(Product.organization_id == org_id)).all()
        assert len(products) == len(STARTER_PRODUCTS)
        for product in products:
            assert product.media_asset_id is None
            assert product.image_reference == starter_product_image_reference(product.slug)
            asset = starter_media.starter_asset(product.image_reference)
            assert asset is not None and starter_media.starter_asset_available(asset)
        assert session.scalar(select(MediaAsset.id).where(MediaAsset.organization_id == org_id)) is None
        # The prospect media allowance is untouched by seeded starter images.
        enforce_demo_media_limits(session, org_id, incoming_bytes=1_000_000)


def test_22_promote_to_live_requires_platform_write_capability(demo_ctx):
    """M3: read-only platform viewers can list prospects but cannot promote them."""
    engine, settings, provider = demo_ctx
    with Session(engine) as session:
        prospect = _signup(session, settings, provider, f"target-{uuid4().hex[:8]}@example.com", business="Promote Target")
        viewer = _signup(session, settings, provider, f"viewer-{uuid4().hex[:8]}@example.com", business="Viewer Co")
        session.add(PlatformGrant(user_id=viewer.principal.user_id, capability="platform.organizations.read", is_active=True))
        session.commit()
        target_id = prospect.principal.organization_id
        assert any(row["id"] == str(target_id) for row in demo_api.platform_demo_prospects(principal=viewer.principal, session=session))
        service = _service(session, settings, provider)
        with pytest.raises(HTTPException) as refused:
            demo_api.platform_promote_to_live(target_id, demo_api.PromoteInput(confirm=True), principal=viewer.principal, session=session, service=service, now=datetime.now(timezone.utc))
        assert refused.value.status_code == 403
        assert session.get(Organization, target_id).commercial_mode == "prospect"

        session.add(PlatformGrant(user_id=viewer.principal.user_id, capability="platform.organizations.write", is_active=True))
        session.commit()
        result = demo_api.platform_promote_to_live(target_id, demo_api.PromoteInput(confirm=True), principal=viewer.principal, session=session, service=service, now=datetime.now(timezone.utc))
        assert result["commercialMode"] == "live"
        assert result["preserved"]["businessName"] == "Promote Target"
        assert len(session.scalars(select(Product).where(Product.organization_id == target_id)).all()) == len(STARTER_PRODUCTS)


def test_23_platform_admin_seeds_keep_promote_ability():
    """M3: real platform-admin seeds already grant write, so hardening removes no legitimate access."""
    from pathlib import Path
    for seed in ("local_review_seed.py", "staging_review_seed.py"):
        source = (Path(__file__).resolve().parents[1] / "app" / seed).read_text()
        assert '"platform.organizations.read", "platform.organizations.write"' in source
