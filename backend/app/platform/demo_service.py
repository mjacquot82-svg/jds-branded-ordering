"""Self-service demo signup, activation requests, funnel events, and promote-to-live."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.jds_auth.config import AuthSettings
from app.jds_auth.models import (
    ExternalIdentity,
    JdsApplication,
    JdsUser,
    Membership,
    MerchantAcquisition,
    Organization,
    Role,
)
from app.jds_auth.provider import IdentityProvider, IdentityProviderError, InvalidCredentialsError
from app.jds_auth.rate_limit import RateLimit, RateLimitExceeded
from app.jds_auth.service import AuthenticationService, IssuedSession, MembershipInactive
from app.platform.commercial import COMMERCIAL_LIVE, COMMERCIAL_PROSPECT
from app.platform.demo_limits import (
    DEMO_PLAN_KEY,
    STANDARD_PLAN_KEY,
    standard_plan_amount_cents,
)
from app.platform.demo_starter import apply_demo_starter
from app.platform.models import (
    BillingPlan,
    BillingPlanPricing,
    DemoActivationRequest,
    DemoFunnelEvent,
    DemoPendingSignup,
    OnboardingState,
    OperationalAuditEvent,
    OrganizationSubscription,
)

ALLOWED_FUNNEL_EVENTS = frozenset(
    {
        "demo_started",
        "logo_added",
        "branding_changed",
        "menu_edited",
        "preview_opened",
        "demo_saved",
        "activation_viewed",
        "activation_requested",
    }
)
PROCESSOR_PREFERENCES = frozenset({"clover", "square", "stripe", "moneris", "other", "not_sure"})
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DEMO_SIGNUP_IP = RateLimit("demo-signup-ip", 8, 60 * 60)
DEMO_ENTER_IP = RateLimit("demo-enter-ip", 20, 60 * 60)
DEMO_ACTIVATION_ORG = RateLimit("demo-activation-org", 3, 24 * 60 * 60)
DEMO_FUNNEL_ORG = RateLimit("demo-funnel-org", 120, 60 * 60)


def enforce_demo_rate_limit(session: Session, pepper: str, policy: RateLimit, identifier: str, *, now: datetime) -> None:
    """Fixed-window limiter compatible with an already-open SQLAlchemy session."""
    from datetime import timedelta

    from sqlalchemy import text

    from app.jds_auth.models import AuthRateLimitBucket
    from app.jds_auth.security import hash_secret

    normalized = identifier.strip().lower() or "unknown"
    key_hash = hash_secret(f"{policy.namespace}:{normalized}", pepper)
    lock_key = int.from_bytes(bytes.fromhex(key_hash[:16]), "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
    bucket = session.get(AuthRateLimitBucket, key_hash)
    if bucket is None or bucket.expires_at <= now:
        session.merge(
            AuthRateLimitBucket(
                key_hash=key_hash,
                lock_key=lock_key,
                window_started_at=now,
                expires_at=now + timedelta(seconds=policy.window_seconds),
                request_count=1,
            )
        )
        return
    if bucket.request_count >= policy.maximum:
        raise RateLimitExceeded(int((bucket.expires_at - now).total_seconds()) + 1)
    bucket.request_count += 1



class DemoServiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PublicPricing:
    plan_key: str
    label: str
    currency: str
    amount_cents: int
    interval: str
    jds_sales_take_percent: int
    disclosure: str


def email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def slugify_business(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    base = re.sub(r"-{2,}", "-", base)
    if len(base) < 3:
        base = f"cafe-{uuid4().hex[:8]}"
    return base[:50]


def ensure_unique_slug(session: Session, desired: str) -> str:
    candidate = desired if SLUG_RE.fullmatch(desired) else slugify_business(desired)
    if session.scalar(select(Organization.id).where(Organization.slug == candidate)) is None:
        return candidate
    for _ in range(20):
        suffix = uuid4().hex[:6]
        trial = f"{candidate[:56]}-{suffix}"[:63]
        if session.scalar(select(Organization.id).where(Organization.slug == trial)) is None:
            return trial
    raise DemoServiceError("slug_unavailable", "Could not allocate a unique storefront slug.")


def public_pricing(session: Session) -> PublicPricing:
    amount = standard_plan_amount_cents()
    currency = "CAD"
    label = "JDS Branded Ordering"
    row = session.get(BillingPlanPricing, STANDARD_PLAN_KEY)
    if row is not None:
        amount = int(row.amount_cents)
        currency = row.currency or "CAD"
        label = row.public_label or label
    # Keep DB row aligned with env override without requiring a migration edit.
    if row is not None and row.amount_cents != standard_plan_amount_cents():
        amount = standard_plan_amount_cents()
    return PublicPricing(
        plan_key=STANDARD_PLAN_KEY,
        label=label,
        currency=currency,
        amount_cents=amount,
        interval="month",
        jds_sales_take_percent=0,
        disclosure=(
            "JDS charges a flat monthly software fee and takes 0% of your sales. "
            "Payment processor fees still apply through your merchant provider "
            "(Clover, Square, Stripe, Moneris, or other)."
        ),
    )


def record_funnel_event(
    session: Session,
    *,
    event_name: str,
    organization_id: UUID | None,
    actor_user_id: UUID | None = None,
    metadata: dict | None = None,
) -> DemoFunnelEvent:
    if event_name not in ALLOWED_FUNNEL_EVENTS:
        raise DemoServiceError("invalid_event", "Unsupported funnel event.")
    event = DemoFunnelEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        event_name=event_name,
        metadata_json=metadata or {},
    )
    session.add(event)
    return event


class DemoFunnelService:
    def __init__(self, session: Session, settings: AuthSettings, provider: IdentityProvider) -> None:
        self.session = session
        self.settings = settings
        self.provider = provider
        self.auth = AuthenticationService(session, provider, settings)

    def _ensure_plans(self) -> None:
        if self.session.get(BillingPlan, DEMO_PLAN_KEY) is None:
            self.session.add(
                BillingPlan(
                    key=DEMO_PLAN_KEY,
                    name="JDS Free Demo",
                    entitlements={
                        "designStudio": True,
                        "demoCatalog": True,
                        "commerce": False,
                        "staff": False,
                        "notifications": False,
                        "loyalty": False,
                        "customDomain": False,
                    },
                )
            )
        if self.session.get(BillingPlan, STANDARD_PLAN_KEY) is None:
            self.session.add(
                BillingPlan(
                    key=STANDARD_PLAN_KEY,
                    name="JDS Branded Ordering",
                    entitlements={
                        "designStudio": True,
                        "demoCatalog": True,
                        "commerce": True,
                        "staff": True,
                        "notifications": True,
                        "loyalty": True,
                        "customDomain": True,
                    },
                )
            )
        self.session.flush()
        if self.session.get(BillingPlanPricing, DEMO_PLAN_KEY) is None:
            self.session.add(
                BillingPlanPricing(
                    plan_key=DEMO_PLAN_KEY,
                    currency="CAD",
                    amount_cents=0,
                    public_label="Free demo",
                )
            )
        if self.session.get(BillingPlanPricing, STANDARD_PLAN_KEY) is None:
            self.session.add(
                BillingPlanPricing(
                    plan_key=STANDARD_PLAN_KEY,
                    currency="CAD",
                    amount_cents=standard_plan_amount_cents(),
                    public_label="JDS Branded Ordering",
                )
            )
        self.session.flush()

    def upsert_pending_signup(
        self,
        *,
        email: str,
        business_name: str,
        contact_name: str,
        desired_slug: str | None,
        now: datetime,
    ) -> DemoPendingSignup:
        normalized = email.strip().lower()
        digest = email_hash(normalized)
        pending = self.session.scalar(select(DemoPendingSignup).where(DemoPendingSignup.email_hash == digest))
        if pending is None:
            pending = DemoPendingSignup(
                email=normalized,
                email_hash=digest,
                business_name=business_name.strip(),
                contact_name=(contact_name or "").strip(),
                desired_slug=desired_slug,
                expires_at=now + timedelta(days=7),
            )
            self.session.add(pending)
        else:
            pending.business_name = business_name.strip()
            pending.contact_name = (contact_name or "").strip()
            pending.desired_slug = desired_slug
            pending.status = "pending"
            pending.expires_at = now + timedelta(days=7)
            pending.claimed_at = None
            pending.claimed_organization_id = None
        self.session.flush()
        return pending

    def provision_prospect(
        self,
        *,
        email: str,
        business_name: str,
        contact_name: str,
        desired_slug: str | None,
        authentication_email_verified: bool,
        issuer: str,
        subject: str,
        now: datetime,
        user_agent: str | None,
    ) -> IssuedSession:
        if not authentication_email_verified:
            raise DemoServiceError("email_verification_required", "Verify your email before entering the demo studio.")
        self._ensure_plans()
        normalized = email.strip().lower()
        display = (contact_name or normalized.split("@", 1)[0]).strip() or "Owner"
        with self.session.begin_nested():
            application = self.session.scalar(
                select(JdsApplication).where(
                    JdsApplication.key == self.settings.application_key,
                    JdsApplication.is_active.is_(True),
                )
            )
            if application is None:
                raise DemoServiceError("application_unavailable", "JDS application is unavailable.")
            owner_role = self.session.scalar(
                select(Role).where(Role.application_id == application.id, Role.key == "owner")
            )
            if owner_role is None:
                raise DemoServiceError("role_unavailable", "Owner role is unavailable.")

            existing_identity = self.session.scalar(
                select(ExternalIdentity).where(
                    ExternalIdentity.issuer == issuer,
                    ExternalIdentity.subject == subject,
                )
            )
            if existing_identity is not None:
                user = self.session.get(JdsUser, existing_identity.user_id)
                membership = self.session.scalar(
                    select(Membership).where(
                        Membership.user_id == user.id,
                        Membership.application_id == application.id,
                        Membership.status == "active",
                    )
                )
                if membership is not None:
                    organization = self.session.get(Organization, membership.organization_id)
                    if organization and organization.commercial_mode == COMMERCIAL_PROSPECT:
                        from app.jds_auth.provider import ProviderAuthentication, ProviderIdentity

                        authentication = ProviderAuthentication(
                            ProviderIdentity(issuer=issuer, subject=subject, email=normalized, email_verified=True, display_name=display),
                            "demo-reenter-evidence",
                        )
                        return self.auth._issue(user, membership, authentication, now, user_agent, False)
                    raise DemoServiceError("account_exists", "An account already exists for this email. Sign in instead.")

            user = self.session.scalar(select(JdsUser).where(JdsUser.primary_email == normalized))
            if user is None:
                user = JdsUser(
                    primary_email=normalized,
                    display_name=display,
                    status="active",
                    email_verified_at=now,
                )
                self.session.add(user)
                self.session.flush()
            else:
                user.display_name = display
                user.email_verified_at = user.email_verified_at or now

            if existing_identity is None:
                self.session.add(
                    ExternalIdentity(
                        user_id=user.id,
                        issuer=issuer,
                        subject=subject,
                        provider="supabase",
                        provider_email=normalized,
                    )
                )

            slug = ensure_unique_slug(self.session, desired_slug or slugify_business(business_name))
            organization = Organization(
                slug=slug,
                name=business_name.strip(),
                lifecycle_status="onboarding",
                commercial_mode=COMMERCIAL_PROSPECT,
            )
            self.session.add(organization)
            self.session.flush()
            membership = Membership(
                organization_id=organization.id,
                application_id=application.id,
                user_id=user.id,
                role_id=owner_role.id,
                status="active",
                joined_at=now,
            )
            self.session.add(membership)
            self.session.flush()
            acquisition = MerchantAcquisition(
                organization_id=organization.id,
                source="self_service_demo",
                status="activated",
                owner_contact_hint=normalized,
                requested_plan_key=DEMO_PLAN_KEY,
                activation_destination="/admin/design",
                provider_metadata={"funnel": "m2_self_service"},
                activated_at=now,
            )
            self.session.add(acquisition)
            self.session.add(
                OnboardingState(
                    organization_id=organization.id,
                    state="in_progress",
                    current_step="look",
                    public_ready=False,
                )
            )
            self.session.add(
                OrganizationSubscription(
                    organization_id=organization.id,
                    plan_key=DEMO_PLAN_KEY,
                    state="trialing",
                    provider="unconfigured",
                )
            )
            apply_demo_starter(self.session, organization.id, business_name=business_name)
            digest = email_hash(normalized)
            pending = self.session.scalar(select(DemoPendingSignup).where(DemoPendingSignup.email_hash == digest))
            if pending is not None:
                pending.status = "claimed"
                pending.claimed_at = now
                pending.claimed_organization_id = organization.id
            record_funnel_event(
                self.session,
                event_name="demo_started",
                organization_id=organization.id,
                actor_user_id=user.id,
                metadata={"source": "self_service_demo"},
            )
            self.session.add(
                OperationalAuditEvent(
                    organization_id=organization.id,
                    scope="platform",
                    actor_user_id=user.id,
                    action="demo.provisioned",
                    target_type="organization",
                    target_id=str(organization.id),
                    outcome="success",
                    metadata_json={"source": "self_service_demo"},
                )
            )
            from app.jds_auth.provider import ProviderAuthentication, ProviderIdentity

            authentication = ProviderAuthentication(
                ProviderIdentity(
                    issuer=issuer,
                    subject=subject,
                    email=normalized,
                    email_verified=True,
                    display_name=display,
                ),
                "demo-signup-evidence",
            )
            issued = self.auth._issue(user, membership, authentication, now, user_agent, False)
        return issued

    def signup(
        self,
        *,
        email: str,
        password: str,
        business_name: str,
        contact_name: str,
        desired_slug: str | None,
        now: datetime,
        user_agent: str | None,
        client_id: str,
    ) -> tuple[str, IssuedSession | None]:
        try:
            enforce_demo_rate_limit(self.session, self.settings.session_pepper, DEMO_SIGNUP_IP, client_id, now=now)
        except RateLimitExceeded as error:
            raise DemoServiceError("rate_limited", f"Too many signup attempts. Retry in {error.retry_after}s.") from error

        normalized = email.strip().lower()
        business = business_name.strip()
        if not (1 <= len(business) <= 200):
            raise DemoServiceError("invalid_business_name", "Enter a business name between 1 and 200 characters.")
        if len(password) < 10:
            raise DemoServiceError("weak_password", "Choose a password with at least 10 characters.")

        self.upsert_pending_signup(
            email=normalized,
            business_name=business,
            contact_name=contact_name,
            desired_slug=desired_slug,
            now=now,
        )
        self.session.commit()

        try:
            identity = self.provider.register_user(
                normalized,
                password,
                f"{self.settings.frontend_url.rstrip('/')}/build/verify",
            )
        except IdentityProviderError as error:
            # Account may already exist at the identity provider — try enter path.
            if "already" in str(error).lower() or "exists" in str(error).lower():
                return self.enter(email=normalized, password=password, now=now, user_agent=user_agent, client_id=client_id)
            raise DemoServiceError("registration_failed", "Unable to create your account right now.") from error

        if not identity.email_verified:
            return "verification_required", None

        try:
            authentication = self.provider.authenticate_password(normalized, password)
        except (InvalidCredentialsError, IdentityProviderError) as error:
            raise DemoServiceError("registration_failed", "Account created but sign-in failed. Verify email, then continue.") from error

        issued = self.provision_prospect(
            email=normalized,
            business_name=business,
            contact_name=contact_name or identity.display_name or "",
            desired_slug=desired_slug,
            authentication_email_verified=authentication.identity.email_verified,
            issuer=authentication.identity.issuer,
            subject=authentication.identity.subject,
            now=now,
            user_agent=user_agent,
        )
        self.session.commit()
        return "ready", issued

    def enter(
        self,
        *,
        email: str,
        password: str,
        now: datetime,
        user_agent: str | None,
        client_id: str,
    ) -> tuple[str, IssuedSession | None]:
        try:
            enforce_demo_rate_limit(self.session, self.settings.session_pepper, DEMO_ENTER_IP, client_id, now=now)
        except RateLimitExceeded as error:
            raise DemoServiceError("rate_limited", f"Too many attempts. Retry in {error.retry_after}s.") from error

        normalized = email.strip().lower()
        try:
            authentication = self.provider.authenticate_password(normalized, password)
        except InvalidCredentialsError as error:
            raise DemoServiceError("authentication_failed", "Email or password is invalid.") from error
        except IdentityProviderError as error:
            raise DemoServiceError("authentication_unavailable", "Sign-in is temporarily unavailable.") from error

        if not authentication.identity.email_verified:
            return "verification_required", None

        existing = self.session.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.issuer == authentication.identity.issuer,
                ExternalIdentity.subject == authentication.identity.subject,
            )
        )
        if existing is not None:
            application = self.session.scalar(
                select(JdsApplication).where(
                    JdsApplication.key == self.settings.application_key,
                    JdsApplication.is_active.is_(True),
                )
            )
            membership = None
            if application is not None:
                membership = self.session.scalar(
                    select(Membership).where(
                        Membership.user_id == existing.user_id,
                        Membership.application_id == application.id,
                        Membership.status == "active",
                    )
                )
            if membership is not None:
                user = self.session.get(JdsUser, existing.user_id)
                if user is not None:
                    issued = self.auth._issue(user, membership, authentication, now, user_agent, False)
                    self.session.commit()
                    return "ready", issued

        pending = self.session.scalar(
            select(DemoPendingSignup).where(
                DemoPendingSignup.email_hash == email_hash(normalized),
                DemoPendingSignup.status == "pending",
            )
        )
        if pending is None or pending.expires_at <= now:
            raise DemoServiceError("signup_required", "Start with Build Your Store Free to create a demo.")

        issued = self.provision_prospect(
            email=normalized,
            business_name=pending.business_name,
            contact_name=pending.contact_name or authentication.identity.display_name or "",
            desired_slug=pending.desired_slug,
            authentication_email_verified=True,
            issuer=authentication.identity.issuer,
            subject=authentication.identity.subject,
            now=now,
            user_agent=user_agent,
        )
        self.session.commit()
        return "ready", issued

    def request_activation(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        business_name: str,
        contact_name: str,
        email: str,
        phone: str | None,
        city: str,
        desired_domain: str | None,
        processor_preference: str,
        now: datetime,
    ) -> DemoActivationRequest:
        organization = self.session.get(Organization, organization_id)
        if organization is None or organization.commercial_mode != COMMERCIAL_PROSPECT:
            raise DemoServiceError("not_a_prospect", "Activation requests are only for free demo stores.")
        preference = (processor_preference or "not_sure").strip().lower()
        if preference not in PROCESSOR_PREFERENCES:
            raise DemoServiceError("invalid_processor", "Choose a valid payment processor preference.")
        try:
            enforce_demo_rate_limit(
                self.session, self.settings.session_pepper, DEMO_ACTIVATION_ORG, str(organization_id), now=now
            )
        except RateLimitExceeded as error:
            raise DemoServiceError("rate_limited", f"Too many activation requests. Retry in {error.retry_after}s.") from error

        open_request = self.session.scalar(
            select(DemoActivationRequest).where(
                DemoActivationRequest.organization_id == organization_id,
                DemoActivationRequest.status.in_(("requested", "in_review")),
            )
        )
        if open_request is not None:
            raise DemoServiceError("already_requested", "An activation request is already open for this demo.")

        pricing = public_pricing(self.session)
        item = DemoActivationRequest(
            organization_id=organization_id,
            requested_by_user_id=user_id,
            business_name=business_name.strip(),
            contact_name=contact_name.strip(),
            email=email.strip().lower(),
            phone=(phone or None),
            city=(city or "").strip(),
            desired_domain=(desired_domain or None),
            processor_preference=preference,
            status="requested",
            quoted_plan_key=pricing.plan_key,
            quoted_amount_cents=pricing.amount_cents,
            quoted_currency=pricing.currency,
        )
        self.session.add(item)
        acquisition = self.session.scalar(
            select(MerchantAcquisition).where(MerchantAcquisition.organization_id == organization_id)
        )
        if acquisition is not None:
            acquisition.status = "activation_pending"
            meta = dict(acquisition.provider_metadata or {})
            meta["activation_request"] = "open"
            acquisition.provider_metadata = meta
        record_funnel_event(
            self.session,
            event_name="activation_requested",
            organization_id=organization_id,
            actor_user_id=user_id,
            metadata={"processor": preference, "plan": pricing.plan_key},
        )
        self.session.add(
            OperationalAuditEvent(
                organization_id=organization_id,
                scope="platform",
                actor_user_id=user_id,
                action="demo.activation_requested",
                target_type="demo_activation_request",
                target_id=str(item.id),
                outcome="success",
                metadata_json={"processor": preference},
            )
        )
        self.session.commit()
        return item

    def promote_to_live(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        now: datetime,
    ) -> Organization:
        """JDS admin only: convert prospect → live while preserving design/catalog/media."""
        organization = self.session.get(Organization, organization_id)
        if organization is None:
            raise DemoServiceError("not_found", "Organization not found.")
        if organization.commercial_mode == COMMERCIAL_LIVE:
            return organization
        self._ensure_plans()
        organization.commercial_mode = COMMERCIAL_LIVE
        # Do not auto-set public_ready; owner still completes payment/hostname launch.
        subscription = self.session.get(OrganizationSubscription, organization_id)
        if subscription is None:
            self.session.add(
                OrganizationSubscription(
                    organization_id=organization_id,
                    plan_key=STANDARD_PLAN_KEY,
                    state="active",
                    provider="manual",
                )
            )
        else:
            subscription.plan_key = STANDARD_PLAN_KEY
            subscription.state = "active"
            subscription.provider = "manual"
        for request in self.session.scalars(
            select(DemoActivationRequest).where(
                DemoActivationRequest.organization_id == organization_id,
                DemoActivationRequest.status.in_(("requested", "in_review")),
            )
        ):
            request.status = "approved"
            request.updated_at = now
        acquisition = self.session.scalar(
            select(MerchantAcquisition).where(MerchantAcquisition.organization_id == organization_id)
        )
        if acquisition is not None:
            acquisition.status = "activated"
            acquisition.activated_at = acquisition.activated_at or now
            acquisition.requested_plan_key = STANDARD_PLAN_KEY
        self.session.add(
            OperationalAuditEvent(
                organization_id=organization_id,
                scope="platform",
                actor_user_id=actor_user_id,
                action="demo.promoted_to_live",
                target_type="organization",
                target_id=str(organization_id),
                outcome="success",
                metadata_json={"preserved": ["design", "catalog", "media", "business_profile"]},
            )
        )
        self.session.commit()
        return organization


def enforce_demo_catalog_limits(session: Session, organization_id: UUID) -> None:
    from app.catalog.models import Category, Product
    from app.platform.commercial import is_prospect
    from app.platform.demo_limits import DEMO_MAX_CATEGORIES, DEMO_MAX_PRODUCTS
    from fastapi import HTTPException

    if not is_prospect(session, organization_id):
        return
    products = session.scalar(
        select(func.count()).select_from(Product).where(
            Product.organization_id == organization_id,
            Product.archived_at.is_(None),
        )
    ) or 0
    if products >= DEMO_MAX_PRODUCTS:
        raise HTTPException(
            403,
            detail={
                "code": "demo_product_limit",
                "message": f"Free demos may include up to {DEMO_MAX_PRODUCTS} menu items.",
                "limit": DEMO_MAX_PRODUCTS,
            },
        )
    categories = session.scalar(
        select(func.count()).select_from(Category).where(Category.organization_id == organization_id)
    ) or 0
    # categories checked at create-category call sites with a separate helper


def enforce_demo_category_limits(session: Session, organization_id: UUID) -> None:
    from app.catalog.models import Category
    from app.platform.commercial import is_prospect
    from app.platform.demo_limits import DEMO_MAX_CATEGORIES
    from fastapi import HTTPException

    if not is_prospect(session, organization_id):
        return
    categories = session.scalar(
        select(func.count()).select_from(Category).where(Category.organization_id == organization_id)
    ) or 0
    if categories >= DEMO_MAX_CATEGORIES:
        raise HTTPException(
            403,
            detail={
                "code": "demo_category_limit",
                "message": f"Free demos may include up to {DEMO_MAX_CATEGORIES} categories.",
                "limit": DEMO_MAX_CATEGORIES,
            },
        )


def enforce_demo_media_limits(session: Session, organization_id: UUID, *, incoming_bytes: int) -> None:
    from app.platform.commercial import is_prospect
    from app.platform.demo_limits import DEMO_MAX_IMAGE_BYTES, DEMO_MAX_MEDIA_FILES, DEMO_MAX_STORAGE_BYTES
    from app.platform.models import MediaAsset
    from fastapi import HTTPException

    if not is_prospect(session, organization_id):
        return
    if incoming_bytes > DEMO_MAX_IMAGE_BYTES:
        raise HTTPException(
            403,
            detail={
                "code": "demo_media_file_too_large",
                "message": f"Demo uploads may be at most {DEMO_MAX_IMAGE_BYTES // (1024 * 1024)} MB each.",
                "limitBytes": DEMO_MAX_IMAGE_BYTES,
            },
        )
    rows = session.scalars(
        select(MediaAsset).where(
            MediaAsset.organization_id == organization_id,
            MediaAsset.status == "active",
        )
    ).all()
    if len(rows) >= DEMO_MAX_MEDIA_FILES:
        raise HTTPException(
            403,
            detail={
                "code": "demo_media_file_limit",
                "message": f"Free demos may upload up to {DEMO_MAX_MEDIA_FILES} images.",
                "limit": DEMO_MAX_MEDIA_FILES,
            },
        )
    used = sum(int(item.byte_size or 0) for item in rows)
    if used + incoming_bytes > DEMO_MAX_STORAGE_BYTES:
        raise HTTPException(
            403,
            detail={
                "code": "demo_media_storage_limit",
                "message": "Free demo storage limit reached. Remove an image or request activation.",
                "limitBytes": DEMO_MAX_STORAGE_BYTES,
                "usedBytes": used,
            },
        )
