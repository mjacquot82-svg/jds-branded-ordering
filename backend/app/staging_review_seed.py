"""Idempotent synthetic data for the persistent staging review environment."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.seed import seed_catalog
from app.db.engine import create_database_engine
from app.jds_auth.foundation import ensure_foundation
from app.jds_auth.models import ExternalIdentity, JdsUser, Membership, Organization, Role
from app.jds_auth.provider import StagingReviewIdentityProvider
from app.local_review_seed import SECOND_CAFE_SLUG, _seed_second_catalog, _seed_tenant_details
from app.platform.models import BillingPlan, OnboardingState, PlatformGrant
from app.platform.readiness import onboarding_completed_steps, synchronize_public_readiness
from app.staging import STAGING_OWNER_EMAIL, assert_staging_seed_safe


def seed_staging_review(database_url: str) -> None:
    assert_staging_seed_safe(database_url)
    frontend_host = urlparse(os.environ["FRONTEND_URL"]).hostname
    if not frontend_host:
        raise RuntimeError("Staging seed requires the configured frontend hostname.")
    application_key = os.environ["JDS_APPLICATION_KEY"]
    engine = create_database_engine(database_url)
    try:
        with Session(engine) as session:
            seed_catalog(session)
        with Session(engine) as session:
            application, ladels = ensure_foundation(
                session,
                application_key=application_key,
                application_name="JDS Commerce — STAGING REVIEW",
                organization_slug="the-guest-house",
                organization_name="The Guest House — TEST",
            )
            _, second = ensure_foundation(
                session,
                application_key=application_key,
                application_name="JDS Commerce — STAGING REVIEW",
                organization_slug=SECOND_CAFE_SLUG,
                organization_name="Second Street Café — TEST",
            )
            owner = session.scalar(select(JdsUser).where(JdsUser.primary_email == STAGING_OWNER_EMAIL))
            if owner is None:
                owner = JdsUser(
                    primary_email=STAGING_OWNER_EMAIL,
                    display_name="Synthetic Staging Review Owner",
                    email_verified_at=datetime.now(timezone.utc),
                )
                session.add(owner)
                session.flush()
            identity = session.scalar(select(ExternalIdentity).where(
                ExternalIdentity.issuer == StagingReviewIdentityProvider.ISSUER,
                ExternalIdentity.subject == StagingReviewIdentityProvider.SUBJECT,
            ))
            if identity is None:
                session.add(ExternalIdentity(
                    user_id=owner.id,
                    issuer=StagingReviewIdentityProvider.ISSUER,
                    subject=StagingReviewIdentityProvider.SUBJECT,
                    provider="staging-review",
                    provider_email=STAGING_OWNER_EMAIL,
                ))
            owner_role = session.scalar(select(Role).where(Role.application_id == application.id, Role.key == "owner"))
            plan = session.get(BillingPlan, "engagement")
            if plan is None:
                session.add(BillingPlan(
                    key="engagement",
                    name="Synthetic Staging Engagement Review",
                    entitlements={"designStudio": True, "notifications": True, "loyalty": True},
                ))
                session.flush()
            for organization in (ladels, second):
                membership = session.scalar(select(Membership).where(
                    Membership.organization_id == organization.id,
                    Membership.application_id == application.id,
                    Membership.user_id == owner.id,
                ))
                if membership is None:
                    session.add(Membership(
                        organization_id=organization.id,
                        application_id=application.id,
                        user_id=owner.id,
                        role_id=owner_role.id,
                        status="active",
                        joined_at=datetime.now(timezone.utc),
                    ))
                else:
                    membership.role_id = owner_role.id
                    membership.status = "active"
            for capability in ("platform.organizations.read", "platform.organizations.write"):
                if session.scalar(select(PlatformGrant).where(PlatformGrant.user_id == owner.id, PlatformGrant.capability == capability)) is None:
                    session.add(PlatformGrant(user_id=owner.id, capability=capability, granted_by_user_id=owner.id))
            _seed_second_catalog(session, second.id)
            _seed_tenant_details(session, ladels, owner, second=False, staging=True, staging_frontend_host=frontend_host)
            _seed_tenant_details(session, second, owner, second=True, staging=True, staging_frontend_host=frontend_host)
            session.commit()
        with Session(engine) as session, session.begin():
            organizations = session.scalars(select(Organization).where(Organization.slug.in_(("the-guest-house", SECOND_CAFE_SLUG))))
            for organization in organizations:
                result = synchronize_public_readiness(session, organization.id)
                onboarding = session.get(OnboardingState, organization.id)
                if onboarding is None:
                    onboarding = OnboardingState(organization_id=organization.id)
                    session.add(onboarding)
                onboarding.completed_steps = onboarding_completed_steps(result)
                onboarding.current_step = "complete"
                onboarding.state = "complete"
                onboarding.public_ready = result.public_ready
    finally:
        engine.dispose()


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")
    seed_staging_review(database_url)
    print("Synthetic persistent staging review data is ready.")


if __name__ == "__main__":
    main()
