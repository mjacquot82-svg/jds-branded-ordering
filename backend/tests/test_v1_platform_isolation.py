from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jds_auth.models import JdsApplication, JdsUser, Organization, Role
from app.availability.models import BusinessHour, BusinessSettings
from app.catalog.models import Category, Product
from app.clover.models import CloverInstallation
from app.platform.design import DEFAULT_CONFIG, DesignService, DesignValidationError
from app.api.v1.platform import (
    OnboardingInput,
    ProvisionOrganizationInput,
    disable_storefront,
    entitlements,
    launch_kit,
    platform_organizations,
    provision_organization,
    retry_storefront,
    save_onboarding,
)
from app.jds_auth.service import AuthPrincipal
from app.loyalty.models import CustomerLoyaltyEvent, LoyaltyProgram
from app.platform.models import BillingPlan, BusinessProfile, CustomerRelationship, DesignMediaReference, DesignVersion, MediaAsset, OnboardingState, OperationalAuditEvent, OrganizationSubscription, PlatformGrant, StorefrontHostname
from app.platform.media import local_media_path, persist_local_image
from app.platform.entitlements import enforce_entitlement
from app.platform.readiness import synchronize_public_readiness
from app.platform.assets import launch_qr_svg, tenant_icon_png
from app.push.models import CustomerNotificationPreference, WebPushSubscription
from app.tenancy.context import TenantContext, TenantResolutionSource
from app.tenancy.resolver import TenantResolutionError, resolve_storefront_context
from tests.test_migrations import make_alembic_config


@pytest.fixture
def platform_db(postgresql_url):
    command.upgrade(make_alembic_config(postgresql_url), "head")
    from sqlalchemy import create_engine
    engine = create_engine(postgresql_url)
    with Session(engine) as session:
        suffix = uuid4().hex
        alpha_host = f"alpha-{suffix}.jdsstudio.ca"; beta_host = f"beta-{suffix}.jdsstudio.ca"
        a = Organization(slug=f"alpha-{uuid4()}", name="Alpha Café", lifecycle_status="active")
        b = Organization(slug=f"beta-{uuid4()}", name="Beta Café", lifecycle_status="active")
        actor = JdsUser(primary_email=f"platform-{uuid4()}@example.com", display_name="Owner")
        session.add_all([a, b, actor]); session.flush()
        if session.get(BillingPlan,"core-test") is None:
            session.add(BillingPlan(key="core-test",name="Core test fixture",entitlements={"designStudio":True}))
        if session.get(BillingPlan,"engagement-test") is None:
            session.add(BillingPlan(key="engagement-test",name="Engagement test fixture",entitlements={"designStudio":True,"notifications":True,"loyalty":True}))
        session.add_all([
            OnboardingState(organization_id=a.id, state="complete", public_ready=True, current_step="complete"),
            OnboardingState(organization_id=b.id, state="complete", public_ready=True, current_step="complete"),
            StorefrontHostname(organization_id=a.id, hostname=alpha_host, status="verified", is_canonical=True),
            StorefrontHostname(organization_id=b.id, hostname=beta_host, status="verified", is_canonical=True),
            CustomerRelationship(organization_id=a.id,user_id=actor.id,display_name="Owner A"),
            CustomerRelationship(organization_id=b.id,user_id=actor.id,display_name="Owner B"),
        ])
        session.commit(); ids = a.id, b.id, actor.id, alpha_host, beta_host
    yield engine, ids
    engine.dispose()


def context(organization_id, slug):
    return TenantContext(organization_id=organization_id, organization_slug=slug, source=TenantResolutionSource.AUTHENTICATED_MEMBERSHIP)


@pytest.mark.postgresql
def test_verified_hostname_resolution_is_exact_and_unknown_hosts_fail_closed(platform_db):
    engine, (a, b, _, alpha_host, beta_host) = platform_db
    with Session(engine) as session:
        assert resolve_storefront_context(session, host=alpha_host).organization_id == a
        assert resolve_storefront_context(session, host=beta_host).organization_id == b
        with pytest.raises(TenantResolutionError):
            resolve_storefront_context(session, host="unknown.example")


@pytest.mark.postgresql
def test_verified_hostname_never_bypasses_authoritative_readiness(platform_db):
    engine, (a, _, _, alpha_host, _) = platform_db
    with Session(engine) as session:
        onboarding = session.get(OnboardingState, a)
        onboarding.public_ready = False
        session.commit()
        with pytest.raises(TenantResolutionError, match="not ready"):
            resolve_storefront_context(session, host=alpha_host)

        onboarding.public_ready = True
        organization = session.get(Organization, a)
        organization.lifecycle_status = "suspended"
        session.commit()
        with pytest.raises(TenantResolutionError, match="not ready"):
            resolve_storefront_context(session, host=alpha_host)


@pytest.mark.postgresql
def test_customer_relationship_and_media_identifiers_are_tenant_scoped(platform_db):
    engine, (a, b, _, _, _) = platform_db
    with Session(engine) as session:
        user = JdsUser(primary_email=f"shared-{uuid4()}@example.com", display_name="Shared Customer")
        session.add(user); session.flush()
        session.add_all([
            CustomerRelationship(organization_id=a, user_id=user.id, display_name="Alpha Customer", phone="+15195550101"),
            CustomerRelationship(organization_id=b, user_id=user.id, display_name="Beta Customer", phone="+15195550202"),
            MediaAsset(organization_id=a, storage_key="brand/logo.png", media_type="image/png", byte_size=100, checksum="a" * 64),
            MediaAsset(organization_id=b, storage_key="brand/logo.png", media_type="image/png", byte_size=200, checksum="b" * 64),
        ]); session.commit()
        assert session.scalar(select(CustomerRelationship.phone).where(CustomerRelationship.organization_id == a, CustomerRelationship.user_id == user.id)) == "+15195550101"
        assert session.scalar(select(CustomerRelationship.phone).where(CustomerRelationship.organization_id == b, CustomerRelationship.user_id == user.id)) == "+15195550202"
        assert session.scalar(select(CustomerRelationship.display_name).where(CustomerRelationship.organization_id == a, CustomerRelationship.user_id == user.id)) == "Alpha Customer"
        assert session.scalar(select(MediaAsset.byte_size).where(MediaAsset.organization_id == a, MediaAsset.storage_key == "brand/logo.png")) == 100


@pytest.mark.postgresql
def test_draft_publish_and_revert_are_isolated_and_append_only(platform_db):
    engine, (a, b, actor, _, _) = platform_db
    with Session(engine) as session:
        # Actor is optional at the model layer for migration/system actions.
        service_a = DesignService(session, context(a, "alpha")); workspace_a = service_a.workspace(); session.commit()
        first = deepcopy(DEFAULT_CONFIG); first["displayName"] = "Alpha Café"
        workspace_a = service_a.save(first, workspace_a.revision, actor)
        published = service_a.publish(actor)
        second = deepcopy(first); second["displayName"] = "Alpha Draft Only"
        service_a.save(second, workspace_a.revision, actor)
        assert session.get(DesignVersion, published.id).config["displayName"] == "Alpha Café"
        service_b = DesignService(session, context(b, "beta")); workspace_b = service_b.workspace(); session.commit()
        with pytest.raises(DesignValidationError): service_b.revert(published.id, actor)
        reverted = service_a.revert(published.id, actor)
        assert reverted.id != published.id and reverted.source_version_id == published.id
        assert workspace_b.published_version_id is None


@pytest.mark.postgresql
def test_design_rejects_media_owned_by_another_tenant(platform_db):
    engine, (a, b, actor, _, _) = platform_db
    with Session(engine) as session:
        media = MediaAsset(organization_id=b, storage_key="hero/shared.webp", media_type="image/webp", byte_size=300, checksum="c" * 64)
        session.add(media); session.commit()
        config = deepcopy(DEFAULT_CONFIG); config["hero"] = {"mode": "image", "mediaId": str(media.id)}
        workspace = DesignService(session, context(a, "alpha")).workspace(); session.commit()
        with pytest.raises(DesignValidationError, match="unavailable"):
            DesignService(session, context(a, "alpha")).save(config, workspace.revision, actor)


@pytest.mark.postgresql
def test_platform_visibility_requires_an_explicit_grant_and_is_audited(platform_db):
    engine, (a, _, actor, _, _) = platform_db
    principal = AuthPrincipal(user_id=actor,membership_id=uuid4(),organization_id=a,application_id=uuid4(),session_id=uuid4(),email="platform@example.com",display_name="Platform",role="owner",permissions=frozenset(),assurance_level="password")
    with Session(engine) as session:
        with pytest.raises(HTTPException) as denied:
            platform_organizations(principal, session)
        assert denied.value.status_code == 403
        session.add(PlatformGrant(user_id=actor,capability="platform.organizations.read",is_active=True));session.commit()
        result = platform_organizations(principal, session)
        assert {item["name"] for item in result} >= {"Alpha Café", "Beta Café"}
        assert session.scalar(select(OperationalAuditEvent.id).where(OperationalAuditEvent.scope=="platform",OperationalAuditEvent.action=="platform.organizations_viewed")) is not None


@pytest.mark.postgresql
def test_platform_provisioning_is_explicit_idempotent_and_not_public(platform_db):
    engine, (a, _, actor, _, _) = platform_db
    principal = AuthPrincipal(user_id=actor,membership_id=uuid4(),organization_id=a,application_id=uuid4(),session_id=uuid4(),email="platform@example.com",display_name="Platform",role="owner",permissions=frozenset(),assurance_level="password")
    with Session(engine) as session:
        session.add(PlatformGrant(user_id=actor,capability="platform.organizations.write",is_active=True));session.commit()
        owner=session.get(JdsUser,actor)
        application = session.scalar(
            select(JdsApplication).where(JdsApplication.key == "jds-commerce")
        )
        if application is None:
            application = JdsApplication(
                key="jds-commerce", name="JDS Commerce", is_active=True
            )
            session.add(application)
            session.flush()
        role = session.scalar(
            select(Role).where(
                Role.application_id == application.id, Role.key == "owner"
            )
        )
        if role is None:
            session.add(Role(application_id=application.id, key="owner", name="Owner"))
        session.commit()
        created=provision_organization(ProvisionOrganizationInput(slug=f"new-{uuid4().hex[:8]}",display_name="New Café",owner_email=owner.primary_email),principal,session)
        assert created["publicReady"] is False and created["status"] == "onboarding"
        onboarding=session.get(OnboardingState,UUID(created["id"]))
        assert onboarding.public_ready is False
        with pytest.raises(HTTPException) as duplicate:
            provision_organization(ProvisionOrganizationInput(slug=created["slug"],display_name="Duplicate",owner_email=owner.primary_email),principal,session)
        assert duplicate.value.status_code == 409


@pytest.mark.postgresql
def test_entitlements_are_resolved_only_for_the_selected_business(platform_db, monkeypatch):
    engine, (a, b, _, _, _) = platform_db
    monkeypatch.setenv("JDS_BILLING_ENFORCEMENT_ENABLED","true")
    with Session(engine) as session:
        session.add_all([
            OrganizationSubscription(organization_id=a,plan_key="engagement-test",state="active"),
            OrganizationSubscription(organization_id=b,plan_key="core-test",state="past_due"),
        ]);session.commit()
        assert entitlements(context(a,"alpha"),session)["features"]["loyalty"] is True
        beta = entitlements(context(b,"beta"),session)
        assert beta["state"] == "past_due" and beta["features"] == {}
        with pytest.raises(HTTPException) as denied:
            enforce_entitlement(session,b,"loyalty")
        assert denied.value.status_code == 403
        enforce_entitlement(session,a,"loyalty")


@pytest.mark.postgresql
def test_onboarding_checklist_cannot_override_server_readiness(platform_db):
    engine, (a, _, actor, _, _) = platform_db
    principal = AuthPrincipal(user_id=actor,membership_id=uuid4(),organization_id=a,application_id=uuid4(),session_id=uuid4(),email="owner@example.com",display_name="Owner",role="owner",permissions=frozenset(),assurance_level="password")
    with Session(engine) as session:
        item = session.get(OnboardingState, a)
        item.state = "in_progress"; item.public_ready = False; item.completed_steps = []; item.current_step = "business"
        session.commit()
        result = save_onboarding(OnboardingInput(revision=item.revision,current_step="complete",completed_steps=["business","storefront","hours","fulfillment","design","catalog","clover"]),principal,context(a,"alpha"),session)
        assert result["state"] == "in_progress"
        assert result["completedSteps"] == ["storefront"]
        assert result["publicReady"] is False
        assert session.get(OnboardingState,a).public_ready is False


def test_local_media_storage_keys_are_tenant_and_asset_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("JDS_LOCAL_MEDIA_ROOT", str(tmp_path))
    tenant_a, tenant_b, asset = uuid4(), uuid4(), uuid4()
    image = b"\x89PNG\r\n\x1a\nlocal-test-image"
    key_a, checksum_a = persist_local_image(tenant_a, asset, image, "image/png")
    key_b, checksum_b = persist_local_image(tenant_b, asset, image, "image/png")
    assert key_a != key_b and key_a.startswith(f"{tenant_a}/") and key_b.startswith(f"{tenant_b}/")
    assert checksum_a == checksum_b
    assert local_media_path(key_a).read_bytes() == image


def test_tenant_pwa_icons_and_launch_qr_are_tenant_specific():
    alpha = tenant_icon_png(192, "#112233", "#abcdef")
    beta = tenant_icon_png(192, "#445566", "#fedcba")
    assert alpha.startswith(b"\x89PNG")
    assert beta.startswith(b"\x89PNG")
    assert alpha != beta
    assert launch_qr_svg("https://alpha.example").startswith(b"<?xml")
    assert launch_qr_svg("https://alpha.example") != launch_qr_svg(
        "https://beta.example"
    )


@pytest.mark.postgresql
def test_hostname_retry_disable_and_launch_assets_are_tenant_bound(
    platform_db, monkeypatch
):
    engine, (a, b, actor, alpha_host, _) = platform_db
    principal = AuthPrincipal(
        user_id=actor,
        membership_id=uuid4(),
        organization_id=a,
        application_id=uuid4(),
        session_id=uuid4(),
        email="owner@example.com",
        display_name="Owner",
        role="owner",
        permissions=frozenset(),
        assurance_level="password",
    )
    monkeypatch.setenv("JDS_STOREFRONT_SCHEME", "https")
    with Session(engine) as session:
        alpha = session.scalar(
            select(StorefrontHostname).where(
                StorefrontHostname.organization_id == a,
                StorefrontHostname.hostname == alpha_host,
            )
        )
        assert launch_kit(context(a, "alpha"), session)["url"] == (
            f"https://{alpha_host}"
        )
        with pytest.raises(HTTPException) as foreign:
            retry_storefront(alpha.id, principal, context(b, "beta"), session)
        assert foreign.value.status_code == 404
        retried = retry_storefront(alpha.id, principal, context(a, "alpha"), session)
        assert retried["status"] == "pending"
        assert session.get(OnboardingState, a).public_ready is False
        disable_storefront(alpha.id, principal, context(a, "alpha"), session)
        assert session.get(StorefrontHostname, alpha.id).status == "disabled"
        assert session.get(OnboardingState, a).public_ready is False


@pytest.mark.postgresql
def test_two_complete_cafes_activate_with_overlapping_business_identifiers_without_leakage(
    platform_db,
):
    engine, (a, b, actor, alpha_host, beta_host) = platform_db
    with Session(engine) as session:
        for organization_id, prefix, template in (
            (a, "Alpha", "cozy"),
            (b, "Beta", "minimal"),
        ):
            settings = BusinessSettings(
                organization_id=organization_id,
                timezone="America/Toronto",
                ordering_enabled=True,
            )
            session.add(settings)
            session.flush()
            session.add_all(
                BusinessHour(
                    organization_id=organization_id,
                    business_settings_id=settings.id,
                    weekday=weekday,
                    is_closed=False,
                    opens_at=time(8),
                    closes_at=time(16),
                )
                for weekday in range(7)
            )
            category = Category(
                organization_id=organization_id,
                slug="coffee",
                name=f"{prefix} Coffee",
                is_published=True,
            )
            session.add(category)
            session.flush()
            session.add_all(
                [
                    Product(
                        organization_id=organization_id,
                        category_id=category.id,
                        slug="latte",
                        name=f"{prefix} Latte",
                        base_price_cents=500,
                        is_published=True,
                    ),
                    BusinessProfile(
                        organization_id=organization_id,
                        display_name=f"{prefix} Café",
                        timezone="America/Toronto",
                        currency="CAD",
                        pickup_instructions=f"Pick up at the {prefix} counter.",
                    ),
                    CloverInstallation(
                        organization_id=organization_id,
                        merchant_id=f"merchant-{prefix.lower()}",
                        environment="sandbox",
                        app_id="fixture-app",
                        access_token_encrypted=f"{prefix}-access-fixture",
                        refresh_token_encrypted=f"{prefix}-refresh-fixture",
                        access_token_expires_at=datetime.now(timezone.utc)
                        + timedelta(hours=1),
                        connection_state="connected",
                    ),
                    LoyaltyProgram(
                        organization_id=organization_id,
                        slug="coffee-club",
                        name=f"{prefix} Coffee Club",
                        description=f"{prefix} rewards",
                        enabled=True,
                        stamps_required=6,
                        reward_description="Free drink",
                        earning_rule="one_per_completed_qualifying_order",
                        reward_type="free_qualifying_product",
                    ),
                    CustomerNotificationPreference(
                        organization_id=organization_id,
                        customer_user_id=actor,
                        notification_kind="lunch_special",
                        enabled=organization_id == b,
                    ),
                ]
            )
            session.flush()
            service = DesignService(session, context(organization_id, prefix.lower()))
            workspace = service.workspace()
            session.commit()
            config = deepcopy(DEFAULT_CONFIG)
            config.update(
                {
                    "displayName": f"{prefix} Café",
                    "template": template,
                    "tagline": f"{prefix} made fresh",
                }
            )
            service.save(config, workspace.revision, actor)
            service.publish(actor)
            result = synchronize_public_readiness(session, organization_id)
            session.commit()
            assert result.public_ready is True

        assert resolve_storefront_context(session, host=alpha_host).organization_id == a
        assert resolve_storefront_context(session, host=beta_host).organization_id == b
        assert session.scalar(
            select(Product.name).where(Product.organization_id == a, Product.slug == "latte")
        ) == "Alpha Latte"
        assert session.scalar(
            select(Product.name).where(Product.organization_id == b, Product.slug == "latte")
        ) == "Beta Latte"
        assert session.scalar(
            select(LoyaltyProgram.name).where(
                LoyaltyProgram.organization_id == a,
                LoyaltyProgram.slug == "coffee-club",
            )
        ) == "Alpha Coffee Club"
        assert session.scalar(
            select(CustomerNotificationPreference.enabled).where(
                CustomerNotificationPreference.organization_id == a,
                CustomerNotificationPreference.customer_user_id == actor,
            )
        ) is False
        assert session.scalar(
            select(CustomerNotificationPreference.enabled).where(
                CustomerNotificationPreference.organization_id == b,
                CustomerNotificationPreference.customer_user_id == actor,
            )
        ) is True
        assert session.scalar(
            select(DesignVersion.config["template"].as_string()).where(
                DesignVersion.organization_id == b
            )
        ) == "minimal"


@pytest.mark.postgresql
def test_database_rejects_cross_tenant_loyalty_and_design_relationships(platform_db):
    engine, (a, b, actor, _, _) = platform_db
    from sqlalchemy.exc import IntegrityError
    from app.platform.models import DesignPublication
    with Session(engine) as session:
        program=LoyaltyProgram(organization_id=a,slug="cross",name="Cross",description="test",enabled=True,stamps_required=6,reward_description="Free",earning_rule="one_per_completed_qualifying_order",reward_type="free_qualifying_product")
        session.add(program);session.flush()
        session.add(CustomerLoyaltyEvent(organization_id=b,customer_user_id=actor,loyalty_program_id=program.id,event_type="manual_adjustment",quantity=1,actor_user_id=actor,reason="reject",program_name_snapshot="Cross"))
        with pytest.raises(IntegrityError): session.commit()
        session.rollback()
        version=DesignService(session,context(a,"alpha")).publish(actor)
        session.add(DesignPublication(organization_id=b,version_id=version.id,action="publish",actor_user_id=actor))
        with pytest.raises(IntegrityError): session.commit()


@pytest.mark.postgresql
def test_active_draft_media_reference_prevents_archive_and_is_tenant_bound(platform_db):
    engine, (a, b, actor, _, _) = platform_db
    from app.api.v1.platform import archive_media
    with Session(engine) as session:
        media=MediaAsset(organization_id=a,storage_key="brand/draft.webp",media_type="image/webp",byte_size=100,checksum="d"*64)
        session.add(media);session.commit()
        service=DesignService(session,context(a,"alpha")); workspace=service.workspace();session.commit()
        config=deepcopy(DEFAULT_CONFIG);config["logoMediaId"]=str(media.id)
        service.save(config,workspace.revision,actor)
        assert session.scalar(select(DesignMediaReference.id).where(DesignMediaReference.organization_id==a,DesignMediaReference.media_asset_id==media.id))
        with pytest.raises(HTTPException) as used: archive_media(media.id,AuthPrincipal(user_id=actor,membership_id=uuid4(),organization_id=a,application_id=uuid4(),session_id=uuid4(),email="a@example.com",display_name="A",role="owner",permissions=frozenset(),assurance_level="password"),context(a,"alpha"),session)
        assert used.value.status_code == 409
        with pytest.raises(HTTPException) as foreign: archive_media(media.id,AuthPrincipal(user_id=actor,membership_id=uuid4(),organization_id=b,application_id=uuid4(),session_id=uuid4(),email="b@example.com",display_name="B",role="owner",permissions=frozenset(),assurance_level="password"),context(b,"beta"),session)
        assert foreign.value.status_code == 404


@pytest.mark.postgresql
def test_concurrent_design_publish_allocates_unique_serial_versions(platform_db):
    engine, (a, _, actor, _, _) = platform_db
    with Session(engine) as session:
        DesignService(session,context(a,"alpha")).workspace();session.commit()
    barrier=Barrier(2)
    def publish_once():
        with Session(engine) as session:
            barrier.wait()
            return DesignService(session,context(a,"alpha")).publish(actor).version_number
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(publish_once) for _ in range(2)]
        versions=sorted([future.result() for future in futures])
    assert versions == [1,2]


@pytest.mark.postgresql
def test_notification_preferences_and_colliding_endpoints_are_tenant_scoped(platform_db):
    engine, (a, b, actor, _, _) = platform_db
    with Session(engine) as session:
        session.add_all([
            CustomerNotificationPreference(organization_id=a,customer_user_id=actor,notification_kind="lunch_special",enabled=True),
            CustomerNotificationPreference(organization_id=b,customer_user_id=actor,notification_kind="lunch_special",enabled=False),
            WebPushSubscription(organization_id=a,customer_user_id=actor,endpoint_ciphertext=b"a",endpoint_fingerprint="same",p256dh_ciphertext=b"a",auth_ciphertext=b"a"),
            WebPushSubscription(organization_id=b,customer_user_id=actor,endpoint_ciphertext=b"b",endpoint_fingerprint="same",p256dh_ciphertext=b"b",auth_ciphertext=b"b"),
        ]);session.commit()
        assert session.scalar(select(CustomerNotificationPreference.enabled).where(CustomerNotificationPreference.organization_id==a,CustomerNotificationPreference.customer_user_id==actor)) is True
        assert session.scalar(select(CustomerNotificationPreference.enabled).where(CustomerNotificationPreference.organization_id==b,CustomerNotificationPreference.customer_user_id==actor)) is False
        assert session.scalar(select(WebPushSubscription.endpoint_ciphertext).where(WebPushSubscription.organization_id==b,WebPushSubscription.endpoint_fingerprint=="same")) == b"b"


@pytest.mark.postgresql
def test_loyalty_programs_and_balances_are_independent_for_one_global_customer(platform_db):
    engine, (a, b, actor, _, _) = platform_db
    with Session(engine) as session:
        programs=[]
        for organization,name in ((a,"Alpha Loyalty"),(b,"Beta Loyalty")):
            item=LoyaltyProgram(organization_id=organization,slug="coffee",name=name,description="Local program",enabled=True,stamps_required=6,reward_description="Free drink",earning_rule="one_per_completed_qualifying_order",reward_type="free_qualifying_product");session.add(item);programs.append(item)
        session.flush()
        session.add_all([
            CustomerLoyaltyEvent(organization_id=a,customer_user_id=actor,loyalty_program_id=programs[0].id,event_type="manual_adjustment",quantity=2,actor_user_id=actor,reason="test fixture",program_name_snapshot=programs[0].name),
            CustomerLoyaltyEvent(organization_id=b,customer_user_id=actor,loyalty_program_id=programs[1].id,event_type="manual_adjustment",quantity=5,actor_user_id=actor,reason="test fixture",program_name_snapshot=programs[1].name),
        ]);session.commit()
        assert session.scalar(select(CustomerLoyaltyEvent.quantity).where(CustomerLoyaltyEvent.organization_id==a,CustomerLoyaltyEvent.customer_user_id==actor)) == 2
        assert session.scalar(select(CustomerLoyaltyEvent.quantity).where(CustomerLoyaltyEvent.organization_id==b,CustomerLoyaltyEvent.customer_user_id==actor)) == 5
