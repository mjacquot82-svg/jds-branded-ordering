from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jds_auth.config import AuthSettings
from app.jds_auth.models import (
    ExternalIdentity, JdsApplication, JdsUser, Membership, MerchantAcquisition,
    MerchantActivation, Organization, Role,
)
from app.jds_auth.provider import IdentityProvider
from app.jds_auth.security import create_secret, hash_secret, secret_matches
from app.jds_auth.service import AuthenticationService, IssuedSession, MembershipInactive
from app.platform.design import DEFAULT_CONFIG
from app.platform.models import DesignWorkspace, OnboardingState, OperationalAuditEvent


ALLOWED_ACQUISITION_SOURCES = frozenset({"clover", "direct", "invitation", "platform", "local_review", "staging_review"})


class AcquisitionError(ValueError):
    pass


class ActivationInvalid(AcquisitionError):
    pass


class ActivationDelivery(Protocol):
    def send(self, email: str, activation_url: str) -> None: ...


class DeferredActivationDelivery:
    """Default adapter: persistence succeeds without selecting an email vendor."""

    def send(self, email: str, activation_url: str) -> None:
        return None


@dataclass(frozen=True)
class AcquisitionRequest:
    slug: str
    display_name: str
    owner_email: str
    source: str
    requested_plan_key: str | None = None
    external_installation_reference: str | None = None
    verified_merchant_reference: str | None = None
    provider_metadata: dict | None = None


@dataclass(frozen=True)
class ProvisionedMerchant:
    acquisition: MerchantAcquisition
    activation: MerchantActivation
    activation_secret: str


class MerchantAcquisitionService:
    def __init__(self, session: Session, settings: AuthSettings) -> None:
        self.session = session
        self.settings = settings

    def provision(self, request: AcquisitionRequest, *, now: datetime, actor_user_id: UUID | None = None, intended_user_id: UUID | None = None, activation_secret: str | None = None) -> ProvisionedMerchant:
        source = request.source.strip().lower()
        if source not in ALLOWED_ACQUISITION_SOURCES:
            raise AcquisitionError("Unsupported acquisition source.")
        email = request.owner_email.strip().lower()
        with self.session.begin_nested():
            application = self.session.scalar(select(JdsApplication).where(JdsApplication.key == self.settings.application_key, JdsApplication.is_active.is_(True)))
            if application is None:
                raise AcquisitionError("JDS application is unavailable.")
            if self.session.scalar(select(Organization.id).where(Organization.slug == request.slug)) is not None:
                raise AcquisitionError("Organization slug is unavailable.")
            owner_role = self.session.scalar(select(Role).where(Role.application_id == application.id, Role.key == "owner"))
            if owner_role is None:
                raise AcquisitionError("Owner role is unavailable.")
            user = self.session.get(JdsUser, intended_user_id) if intended_user_id else self.session.scalar(select(JdsUser).where(JdsUser.primary_email == email))
            if user is None:
                user = JdsUser(primary_email=email, display_name=email.split("@", 1)[0], status="active")
                self.session.add(user)
                self.session.flush()
            if user.primary_email != email:
                raise AcquisitionError("Intended owner does not match the acquisition contact.")
            organization = Organization(slug=request.slug, name=request.display_name.strip(), lifecycle_status="onboarding")
            self.session.add(organization)
            self.session.flush()
            membership = Membership(organization_id=organization.id, application_id=application.id, user_id=user.id, role_id=owner_role.id, status="invited")
            self.session.add(membership)
            self.session.flush()
            acquisition = MerchantAcquisition(
                organization_id=organization.id, source=source, status="activation_pending",
                external_installation_reference=request.external_installation_reference,
                verified_merchant_reference=request.verified_merchant_reference,
                owner_contact_hint=email, requested_plan_key=request.requested_plan_key,
                provider_metadata=request.provider_metadata or {}, provisioned_by_user_id=actor_user_id,
            )
            self.session.add(acquisition)
            self.session.flush()
            secret = activation_secret or create_secret()
            activation = MerchantActivation(
                acquisition_id=acquisition.id, organization_id=organization.id,
                membership_id=membership.id, intended_user_id=user.id, intended_email=email,
                secret_hash=hash_secret(secret, self.settings.session_pepper), expires_at=now + timedelta(hours=24),
            )
            self.session.add_all([
                activation,
                OnboardingState(organization_id=organization.id, state="in_progress", current_step="welcome", public_ready=False),
                DesignWorkspace(organization_id=organization.id, draft_config=dict(DEFAULT_CONFIG), updated_by_user_id=user.id),
                OperationalAuditEvent(organization_id=organization.id, scope="platform", actor_user_id=actor_user_id, action="merchant.provisioned", target_type="acquisition", target_id=str(acquisition.id), outcome="success", metadata_json={"source": source}),
            ])
        return ProvisionedMerchant(acquisition, activation, secret)

    def inspect_activation(self, secret: str, *, now: datetime) -> tuple[MerchantActivation, Organization]:
        activation = self.session.scalar(select(MerchantActivation).where(MerchantActivation.secret_hash == hash_secret(secret, self.settings.session_pepper)))
        if activation is None or activation.status != "pending" or activation.expires_at <= now or not secret_matches(secret, activation.secret_hash, self.settings.session_pepper):
            raise ActivationInvalid("Activation is invalid or expired.")
        organization = self.session.get(Organization, activation.organization_id)
        if organization is None or not organization.is_active:
            raise ActivationInvalid("Activation is invalid or expired.")
        return activation, organization

    def activate_with_password(self, secret: str, email: str, password: str, provider: IdentityProvider, *, now: datetime, user_agent: str | None) -> IssuedSession:
        authentication = provider.authenticate_password(email.strip().lower(), password)
        if not authentication.identity.email_verified:
            raise ActivationInvalid("A verified identity is required.")
        with self.session.begin_nested():
            activation = self.session.scalar(select(MerchantActivation).where(MerchantActivation.secret_hash == hash_secret(secret, self.settings.session_pepper)).with_for_update())
            if activation is None or activation.status != "pending" or activation.expires_at <= now or not secret_matches(secret, activation.secret_hash, self.settings.session_pepper):
                raise ActivationInvalid("Activation is invalid or expired.")
            expected = activation.intended_email.strip().lower()
            if authentication.identity.email.strip().lower() != expected or email.strip().lower() != expected:
                raise ActivationInvalid("Activation is not valid for this identity.")
            membership = self.session.get(Membership, activation.membership_id, with_for_update=True)
            user = self.session.get(JdsUser, activation.intended_user_id, with_for_update=True)
            acquisition = self.session.get(MerchantAcquisition, activation.acquisition_id, with_for_update=True)
            if membership is None or user is None or acquisition is None or membership.user_id != user.id or membership.organization_id != activation.organization_id or acquisition.organization_id != activation.organization_id:
                raise ActivationInvalid("Activation scope is invalid.")
            existing_identity = self.session.scalar(select(ExternalIdentity).where(ExternalIdentity.issuer == authentication.identity.issuer, ExternalIdentity.subject == authentication.identity.subject))
            if existing_identity is not None and existing_identity.user_id != user.id:
                raise ActivationInvalid("Identity is already bound to another account.")
            if existing_identity is None:
                self.session.add(ExternalIdentity(user_id=user.id, issuer=authentication.identity.issuer, subject=authentication.identity.subject, provider="supabase", provider_email=expected))
            membership.status = "active"
            membership.joined_at = now
            user.email_verified_at = user.email_verified_at or now
            user.last_authenticated_at = now
            activation.status = "used"
            activation.used_at = now
            acquisition.status = "activated"
            acquisition.activated_at = now
            issued = AuthenticationService(self.session, provider, self.settings)._issue(user, membership, authentication, now, user_agent, False)
            self.session.add(OperationalAuditEvent(organization_id=activation.organization_id, scope="tenant", actor_user_id=user.id, action="merchant.activation_completed", target_type="activation", target_id=str(activation.id), outcome="success", metadata_json={"source": acquisition.source}))
        return issued

    def issue_activation(self, acquisition: MerchantAcquisition, membership: Membership, user: JdsUser, *, now: datetime, secret: str | None = None) -> tuple[MerchantActivation, str]:
        if membership.organization_id != acquisition.organization_id or membership.user_id != user.id:
            raise MembershipInactive("Activation scope is invalid.")
        raw = secret or create_secret()
        activation = MerchantActivation(acquisition_id=acquisition.id, organization_id=acquisition.organization_id, membership_id=membership.id, intended_user_id=user.id, intended_email=user.primary_email, secret_hash=hash_secret(raw, self.settings.session_pepper), expires_at=now + timedelta(hours=24))
        self.session.add(activation)
        acquisition.status = "activation_pending"
        return activation, raw
