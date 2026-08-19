from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.availability.models import BusinessHour, BusinessSettings
from app.catalog.models import Product
from app.clover.models import CloverInstallation
from app.jds_auth.models import Organization
from app.platform.models import BusinessProfile, DesignWorkspace, StorefrontHostname


@dataclass(frozen=True)
class ReadinessResult:
    checks: dict[str, bool]

    @property
    def public_ready(self) -> bool:
        return all(self.checks.values())


def evaluate_storefront_readiness(session: Session, organization_id: UUID) -> ReadinessResult:
    organization = session.get(Organization, organization_id)
    profile = session.get(BusinessProfile, organization_id)
    settings = session.scalar(select(BusinessSettings).where(BusinessSettings.organization_id == organization_id))
    checks = {
        "organization": bool(organization and organization.is_active and organization.lifecycle_status == "active"),
        "business_profile": bool(
            profile and profile.display_name.strip() and profile.pickup_instructions.strip()
            and profile.timezone.strip() and profile.currency.strip()
        ),
        "verified_hostname": session.scalar(select(func.count()).select_from(StorefrontHostname).where(
            StorefrontHostname.organization_id == organization_id,
            StorefrontHostname.status == "verified",
            StorefrontHostname.is_canonical.is_(True),
        )) == 1,
        "fulfillment": bool(settings and settings.ordering_enabled),
        "hours": bool(settings and session.scalar(select(func.count()).select_from(BusinessHour).where(
            BusinessHour.organization_id == organization_id,
            BusinessHour.business_settings_id == settings.id,
        )) == 7),
        "catalog": bool(session.scalar(select(Product.id).where(
            Product.organization_id == organization_id,
            Product.is_published.is_(True),
            Product.archived_at.is_(None),
        ).limit(1))),
        "published_design": bool(
            (workspace := session.get(DesignWorkspace, organization_id))
            and workspace.published_version_id
        ),
        "clover": bool(session.scalar(select(CloverInstallation.id).where(
            CloverInstallation.organization_id == organization_id,
            CloverInstallation.connection_state == "connected",
        ).limit(1))),
    }
    return ReadinessResult(checks=checks)


def synchronize_public_readiness(session: Session, organization_id: UUID) -> ReadinessResult:
    from app.platform.models import OnboardingState

    result = evaluate_storefront_readiness(session, organization_id)
    onboarding = session.get(OnboardingState, organization_id)
    if onboarding is not None:
        onboarding.public_ready = result.public_ready
    return result
