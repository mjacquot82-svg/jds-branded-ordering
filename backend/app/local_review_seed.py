"""Idempotent, development-only data for the local V1 hands-on review."""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.availability.models import BusinessClosure, BusinessHour, BusinessSettings
from app.catalog.models import Category, ModifierGroup, ModifierOption, Product, ProductModifierGroup, SelectionType
from app.catalog.seed import seed_catalog
from app.clover.models import CloverInstallation
from app.db.engine import create_database_engine
from app.jds_auth.foundation import ensure_foundation
from app.jds_auth.models import ExternalIdentity, JdsUser, Membership, Organization, Role
from app.jds_auth.provider import DevelopmentIdentityProvider
from app.platform.design import DEFAULT_CONFIG, DesignService
from app.platform.models import BillingPlan, BusinessProfile, DesignVersion, OnboardingState, OrganizationSubscription, PlatformGrant, StorefrontHostname
from app.platform.readiness import onboarding_completed_steps, synchronize_public_readiness
from app.tenancy.context import TenantContext, TenantResolutionSource

LOCAL_OWNER_EMAIL = "owner@local.jds.test"
SECOND_CAFE_SLUG = "second-street-cafe"


def assert_safe_local_review(database_url: str) -> None:
    parsed = urlparse(database_url.replace("postgresql+psycopg", "postgresql", 1))
    if os.getenv("JDS_ENVIRONMENT", "").lower() != "development" or os.getenv("JDS_ENABLE_LOCAL_REVIEW", "false").lower() != "true":
        raise RuntimeError("Local review seed requires explicit development review mode.")
    if parsed.hostname not in {"127.0.0.1", "localhost"} or not (parsed.path or "").endswith("_local_review"):
        raise RuntimeError("Local review seed accepts only a localhost database ending in _local_review.")


def _tenant(organization) -> TenantContext:
    return TenantContext(organization_id=organization.id, organization_slug=organization.slug, source=TenantResolutionSource.AUTHENTICATED_MEMBERSHIP)


def _seed_hours(session: Session, organization_id, *, opens: time, closes: time) -> None:
    settings = session.scalar(select(BusinessSettings).where(BusinessSettings.organization_id == organization_id))
    if settings is None:
        settings = BusinessSettings(organization_id=organization_id, timezone="America/Toronto")
        session.add(settings); session.flush()
    settings.ordering_enabled = True; settings.ordering_mode = "schedule"
    existing = {row.weekday: row for row in session.scalars(select(BusinessHour).where(BusinessHour.organization_id == organization_id))}
    for weekday in range(7):
        row = existing.get(weekday)
        if row is None:
            row = BusinessHour(organization_id=organization_id, business_settings_id=settings.id, weekday=weekday)
            session.add(row)
        row.is_closed = False; row.opens_at = opens; row.closes_at = closes


def _seed_second_catalog(session: Session, organization_id) -> None:
    categories = {}
    for order, (slug, name) in enumerate((("coffee", "Coffee bar"), ("bakery", "Bakes"))):
        row = session.scalar(select(Category).where(Category.organization_id == organization_id, Category.slug == slug))
        if row is None:
            row = Category(organization_id=organization_id, slug=slug); session.add(row)
        row.name = name; row.description = "Synthetic local review menu."; row.is_published = True; row.sort_order = order
        categories[slug] = row
    session.flush()
    group = session.scalar(select(ModifierGroup).where(ModifierGroup.organization_id == organization_id, ModifierGroup.key == "milk"))
    if group is None:
        group = ModifierGroup(organization_id=organization_id, key="milk"); session.add(group)
    group.name = "Milk choice"; group.selection_type = SelectionType.SINGLE; group.is_required = False
    group.minimum_selections = 0; group.maximum_selections = 1; group.is_active = True; group.sort_order = 0
    session.flush()
    for order, (key, name, price) in enumerate((("whole", "Whole milk", 0), ("oat", "Oat milk", 75))):
        option = session.scalar(select(ModifierOption).where(ModifierOption.modifier_group_id == group.id, ModifierOption.key == key))
        if option is None:
            option = ModifierOption(modifier_group_id=group.id, key=key); session.add(option)
        option.name = name; option.price_adjustment_cents = price; option.is_active = True; option.sort_order = order
    for order, (slug, category, name, price) in enumerate((("latte", "coffee", "Latte", 495), ("croissant", "bakery", "Butter Croissant", 425), ("maple-scone", "bakery", "Maple Scone", 450))):
        product = session.scalar(select(Product).where(Product.organization_id == organization_id, Product.slug == slug))
        if product is None:
            product = Product(organization_id=organization_id, slug=slug); session.add(product)
        product.category_id = categories[category].id; product.name = name; product.description = "Prepared for the local V1 review."
        product.base_price_cents = price; product.image_reference = "coffee" if category == "coffee" else "pastry"
        product.is_published = True; product.is_featured = order < 2; product.sort_order = order; product.archived_at = None
        session.flush()
        if slug == "latte" and session.scalar(select(ProductModifierGroup).where(ProductModifierGroup.product_id == product.id, ProductModifierGroup.modifier_group_id == group.id)) is None:
            session.add(ProductModifierGroup(product_id=product.id, modifier_group_id=group.id, is_active=True, sort_order=0))


def _seed_tenant_details(
    session: Session,
    organization,
    owner: JdsUser,
    *,
    second: bool,
    staging: bool = False,
    staging_frontend_host: str | None = None,
) -> None:
    profile = session.get(BusinessProfile, organization.id)
    if profile is None:
        profile = BusinessProfile(organization_id=organization.id, display_name=organization.name); session.add(profile)
    base_name = "Second Street Café" if second else "The Guest House"
    profile.display_name = f"{base_name} — TEST" if staging else base_name
    profile.legal_name = "Synthetic STAGING Review Merchant — NOT A REAL BUSINESS" if staging else ("Synthetic Local Review Merchant" if second else "Ladel's / The Guest House")
    profile.contact_email = "noreply@staging-review.jds.invalid" if staging else ("hello@second-street.local.test" if second else "hello@local.jds.test")
    profile.timezone = "America/Toronto"; profile.currency = "CAD"
    profile.pickup_instructions = "Pick up at the blue review counter." if second else "Pick up your order at the café counter."
    _seed_hours(session, organization.id, opens=time(7 if second else 8), closes=time(15 if second else 16))
    installation = session.scalar(select(CloverInstallation).where(CloverInstallation.organization_id == organization.id, CloverInstallation.environment == "sandbox"))
    if installation is None:
        installation = CloverInstallation(organization_id=organization.id, merchant_id=f"{'fixture-disabled' if staging else 'local'}-{organization.slug}", environment="sandbox", app_id="staging-fixture-disabled" if staging else "local-review", access_token_encrypted="fixture-disabled-not-a-token" if staging else "synthetic-local-token", refresh_token_encrypted="fixture-disabled-not-a-refresh-token" if staging else "synthetic-local-refresh", access_token_expires_at=datetime.now(timezone.utc) + timedelta(days=3650))
        session.add(installation)
    installation.connection_state = "connected"
    local_hostname = (
        "second-street-cafe.staging.invalid"
        if staging and second
        else staging_frontend_host
        if staging and staging_frontend_host
        else "second-street.localhost"
        if second
        else "the-guest-house.localhost"
    )
    hostname = session.scalar(select(StorefrontHostname).where(StorefrontHostname.hostname == local_hostname))
    if hostname is None:
        session.add(StorefrontHostname(organization_id=organization.id, hostname=local_hostname, status="verified", is_canonical=True, verified_at=datetime.now(timezone.utc)))
    settings = session.scalar(select(BusinessSettings).where(BusinessSettings.organization_id == organization.id))
    closure = session.scalar(select(BusinessClosure).where(BusinessClosure.organization_id == organization.id, BusinessClosure.business_date == date(2099, 1, 1)))
    if closure is None and settings is not None:
        session.add(BusinessClosure(organization_id=organization.id, business_settings_id=settings.id, business_date=date(2099, 1, 1), reopens_on=date(2099, 1, 2), reason="Synthetic staging closure fixture" if staging else "Synthetic local review closure fixture"))
    subscription = session.get(OrganizationSubscription, organization.id)
    if subscription is None:
        session.add(OrganizationSubscription(organization_id=organization.id, plan_key="engagement", state="active", provider="local"))
    session.flush()
    service = DesignService(session, _tenant(organization)); workspace = service.workspace()
    desired = dict(DEFAULT_CONFIG)
    desired.update({
        "template": "modern" if second else "cozy",
        "displayName": profile.display_name,
        "tagline": ("STAGING — NO REAL TRANSACTIONS" if staging else ("Bright coffee, baked locally" if second else "Café & Pantry")),
        "typography": "modern" if second else "classic",
        "colors": ({"primary":"#234f4c","accent":"#d9894d","background":"#f4f0e8","surface":"#ffffff","text":"#18302e"} if second else DEFAULT_CONFIG["colors"]),
        "pwa": ({"shortName":"Second St","themeColor":"#234f4c","backgroundColor":"#f4f0e8"} if second else {"shortName":"Guest House","themeColor":"#6f7d5f","backgroundColor":"#f7f0e6"}),
    })
    published = session.get(DesignVersion, workspace.published_version_id) if workspace.published_version_id else None
    workspace.draft_config = desired
    if published is None or published.config != desired:
        service.publish(owner.id)


def seed_local_review(database_url: str) -> None:
    assert_safe_local_review(database_url)
    engine = create_database_engine(database_url)
    try:
        with Session(engine) as session:
            seed_catalog(session)
        with Session(engine) as session:
            application, ladels = ensure_foundation(session, application_key="jds-commerce", application_name="JDS Commerce", organization_slug="the-guest-house", organization_name="The Guest House")
            _, second = ensure_foundation(session, application_key="jds-commerce", application_name="JDS Commerce", organization_slug=SECOND_CAFE_SLUG, organization_name="Second Street Café")
            owner = session.scalar(select(JdsUser).where(JdsUser.primary_email == LOCAL_OWNER_EMAIL))
            if owner is None:
                owner = JdsUser(primary_email=LOCAL_OWNER_EMAIL, display_name="Local Review Owner", email_verified_at=datetime.now(timezone.utc)); session.add(owner); session.flush()
            identity = session.scalar(select(ExternalIdentity).where(ExternalIdentity.issuer == DevelopmentIdentityProvider.ISSUER, ExternalIdentity.subject == DevelopmentIdentityProvider.SUBJECT))
            if identity is None:
                session.add(ExternalIdentity(user_id=owner.id, issuer=DevelopmentIdentityProvider.ISSUER, subject=DevelopmentIdentityProvider.SUBJECT, provider="development", provider_email=LOCAL_OWNER_EMAIL))
            owner_role = session.scalar(select(Role).where(Role.application_id == application.id, Role.key == "owner"))
            plan = session.get(BillingPlan, "engagement")
            if plan is None:
                session.add(BillingPlan(
                    key="engagement", name="Local Engagement Review",
                    entitlements={"designStudio": True, "notifications": True, "loyalty": True},
                ))
                session.flush()
            for organization in (ladels, second):
                membership = session.scalar(select(Membership).where(Membership.organization_id == organization.id, Membership.application_id == application.id, Membership.user_id == owner.id))
                if membership is None:
                    session.add(Membership(organization_id=organization.id, application_id=application.id, user_id=owner.id, role_id=owner_role.id, status="active", joined_at=datetime.now(timezone.utc)))
                else:
                    membership.role_id = owner_role.id; membership.status = "active"
            for capability in ("platform.organizations.read", "platform.organizations.write"):
                if session.scalar(select(PlatformGrant).where(PlatformGrant.user_id == owner.id, PlatformGrant.capability == capability)) is None:
                    session.add(PlatformGrant(user_id=owner.id, capability=capability, granted_by_user_id=owner.id))
            _seed_second_catalog(session, second.id)
            _seed_tenant_details(session, ladels, owner, second=False)
            _seed_tenant_details(session, second, owner, second=True)
            session.commit()
        with Session(engine) as session, session.begin():
            for organization in session.scalars(select(Organization).where(Organization.slug.in_(("the-guest-house", SECOND_CAFE_SLUG)))):
                result = synchronize_public_readiness(session, organization.id)
                onboarding = session.get(OnboardingState, organization.id)
                if onboarding is None:
                    onboarding = OnboardingState(organization_id=organization.id); session.add(onboarding)
                onboarding.completed_steps = onboarding_completed_steps(result); onboarding.current_step = "complete"; onboarding.state = "complete"; onboarding.public_ready = result.public_ready
    finally:
        engine.dispose()


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")
    seed_local_review(database_url)
    print("Safe local V1 review data is ready.")


if __name__ == "__main__":
    main()
