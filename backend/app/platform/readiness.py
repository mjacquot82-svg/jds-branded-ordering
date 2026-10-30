from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.availability.models import BusinessHour, BusinessSettings
from app.catalog.models import Category, Product
from app.availability.models import ProductAvailability
from app.jds_auth.models import Organization
from app.payments.service import is_payment_connected


def pay_at_pickup_enabled(session: Session, organization_id: UUID) -> bool:
    from app.payments.models import OrganizationOrderSettings

    row = session.get(OrganizationOrderSettings, organization_id)
    return bool(row and row.pay_at_pickup_enabled)


def square_available() -> bool:
    """True only when the platform has every JDS_SQUARE_* value configured."""
    from app.square.config import SquareSettings

    return SquareSettings.from_env().is_configured


def payment_provider_summary(session: Session, organization_id: UUID) -> dict:
    """Non-secret provider info for owner screens: chosen provider + Square health."""
    from app.payments.models import OrganizationPaymentSettings

    settings = session.get(OrganizationPaymentSettings, organization_id)
    square_health = None
    if square_available():
        from app.payments.adapters.square_adapter import SquarePaymentProvider

        square_health = SquarePaymentProvider().connection_status(session, organization_id).health
    return {
        "selectedProvider": settings.provider_key if settings else None,
        "squareHealth": square_health,
    }


def clover_available() -> bool:
    """True only when the platform has Clover app credentials configured."""
    from app.clover.config import CloverConfigurationError, CloverSettings

    try:
        CloverSettings.from_env().validate()
    except (CloverConfigurationError, ValueError):
        return False
    return True
from app.platform.models import BusinessProfile, DesignWorkspace, StorefrontHostname


@dataclass(frozen=True)
class ReadinessResult:
    checks: dict[str, bool]

    @property
    def public_ready(self) -> bool:
        # Ignore deprecated alias keys when computing readiness.
        return all(
            value
            for key, value in self.checks.items()
            if key != "clover"  # alias of payment_connected
        )


def evaluate_storefront_readiness(session: Session, organization_id: UUID) -> ReadinessResult:
    organization = session.get(Organization, organization_id)
    profile = session.get(BusinessProfile, organization_id)
    settings = session.scalar(select(BusinessSettings).where(BusinessSettings.organization_id == organization_id))
    # A shop can take orders with an electronic provider OR with pay at pickup
    # turned on. Payment stays pluggable: Clover is one provider, not a must.
    payment_ok = is_payment_connected(session, organization_id) or pay_at_pickup_enabled(session, organization_id)
    checks = {
        "organization": bool(organization and organization.is_active and organization.lifecycle_status == "active" and getattr(organization, "commercial_mode", "live") == "live"),
        "business_profile": bool(
            profile and profile.display_name.strip() and profile.timezone.strip()
            and profile.currency.strip() and profile.fulfillment_wording.strip()
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
        "catalog": bool(session.scalar(select(Product.id).join(
            Category,
            (Category.id == Product.category_id) &
            (Category.organization_id == Product.organization_id),
        ).outerjoin(
            ProductAvailability,
            (ProductAvailability.product_id == Product.id) &
            (ProductAvailability.organization_id == Product.organization_id),
        ).where(
            Product.organization_id == organization_id,
            Product.is_published.is_(True),
            Product.archived_at.is_(None),
            Category.is_published.is_(True),
            func.coalesce(ProductAvailability.default_available, True).is_(True),
        ).limit(1))),
        "published_design": bool(
            (workspace := session.get(DesignWorkspace, organization_id))
            and workspace.published_version_id
        ),
        # Canonical readiness key (M1). "clover" retained as deprecated alias.
        "payment_connected": payment_ok,
        "clover": payment_ok,
    }
    return ReadinessResult(checks=checks)


def synchronize_public_readiness(session: Session, organization_id: UUID) -> ReadinessResult:
    from app.platform.models import OnboardingState

    result = evaluate_storefront_readiness(session, organization_id)
    onboarding = session.get(OnboardingState, organization_id)
    if onboarding is not None:
        onboarding.public_ready = result.public_ready
    return result


def evaluate_publish_readiness(session: Session, organization_id: UUID) -> ReadinessResult:
    """Requirements that must exist before the first immutable publication.

    Hostname activation, lifecycle activation, and the published pointer are final
    launch outcomes, so they cannot be prerequisites of the first publication.
    """
    launch = evaluate_storefront_readiness(session, organization_id)
    return ReadinessResult(checks={
        key: value for key, value in launch.checks.items()
        if key in {"business_profile", "fulfillment", "hours", "catalog", "payment_connected"}
    })


def onboarding_completed_steps(result: ReadinessResult) -> list[str]:
    mapping = {
        "business": "business_profile", "storefront": "verified_hostname",
        "hours": "hours", "fulfillment": "fulfillment",
        "design": "published_design", "catalog": "catalog",
        # Prefer payments; keep clover as accepted alias in completed_steps lists.
        "payments": "payment_connected",
        "clover": "payment_connected",
    }
    return [step for step, check in mapping.items() if result.checks.get(check, False)]
