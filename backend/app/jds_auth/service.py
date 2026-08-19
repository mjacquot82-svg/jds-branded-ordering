from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from uuid import UUID
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.jds_auth.audit import DatabaseSecurityAuditWriter
from app.jds_auth.config import AuthSettings
from app.jds_auth.models import ExternalIdentity, JdsApplication, JdsUser, Membership, Organization, OwnerInvitation, OwnerSession, Role
from app.jds_auth.provider import IdentityProvider, ProviderAuthentication, ProviderIdentity
from app.jds_auth.repository import AuthRepository
from app.jds_auth.security import create_secret, hash_secret, secret_matches
from app.platform.models import CustomerRelationship


logger = logging.getLogger(__name__)


class AuthenticationError(ValueError):
    code = "authentication_failed"


class CustomerRegistrationError(AuthenticationError):
    def __init__(self, message: str, *, stage: str, reason: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.reason = reason


class CustomerVerificationError(AuthenticationError):
    def __init__(self, message: str, *, stage: str, reason: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.reason = reason


class EmailVerificationRequired(AuthenticationError):
    code = "email_verification_required"


class MembershipInactive(AuthenticationError):
    code = "membership_inactive"


class SessionInvalid(AuthenticationError):
    code = "session_invalid"


class CsrfInvalid(AuthenticationError):
    code = "csrf_invalid"


class InvitationInvalid(AuthenticationError):
    code = "invitation_invalid"


@dataclass(frozen=True)
class AuthPrincipal:
    user_id: UUID
    membership_id: UUID
    organization_id: UUID
    application_id: UUID
    session_id: UUID
    email: str
    display_name: str
    role: str
    permissions: frozenset[str]
    assurance_level: str


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf_token: str
    principal: AuthPrincipal
    absolute_expires_at: datetime


class AuthenticationService:
    def __init__(self, session: Session, provider: IdentityProvider, settings: AuthSettings, *, organization_id: UUID | None = None) -> None:
        self._session = session
        self._provider = provider
        self._settings = settings
        self._organization_id = organization_id
        self._repo = AuthRepository(session)
        self._audit = DatabaseSecurityAuditWriter(session)
        self.registration_stage = "not_started"
        self.verification_stage = "not_started"
        self.password_reset_stage = "not_started"
        self.login_stage = "not_started"

    def login(self, email: str, password: str, *, now: datetime, user_agent: str | None, allowed_roles: frozenset[str] | None = None, persistent: bool = False) -> IssuedSession:
        logger.warning("customer_login_started")
        try:
            self.login_stage = "supabase_password_authentication"
            authentication = self._provider.authenticate_password(email, password)
            self.login_stage = "email_verification_validation"
            if not authentication.identity.email_verified:
                raise EmailVerificationRequired("Email verification is required.")
            with self._session.begin():
                self.login_stage = "local_identity_lookup"
                identity = self._repo.identity(authentication.identity.issuer, authentication.identity.subject)
                logger.warning(
                    "customer_login_local_identity_lookup outcome=%s",
                    "found" if identity is not None else "not_found",
                )
                if identity is None:
                    logger.warning("customer_login_credential_state_validation outcome=skipped reason=identity_not_found")
                    raise MembershipInactive("An active JDS membership is required.")
                self.login_stage = "credential_state_validation"
                credential_active = identity.user.status == "active" and identity.user.credential_state == "active"
                logger.warning(
                    "customer_login_credential_state_validation outcome=%s",
                    "active" if credential_active else "inactive",
                )
                if not credential_active:
                    raise MembershipInactive("An active JDS membership is required.")
                self.login_stage = "application_scope_lookup"
                application, organization = self._scope()
                self.login_stage = "customer_membership_lookup"
                membership = self._repo.active_membership(identity.user_id, application.id, organization.id)
                if membership is None and allowed_roles == frozenset({"customer"}):
                    role = self._repo.role_by_key(application.id, "customer")
                    if role is not None:
                        membership = Membership(
                            organization_id=organization.id, application_id=application.id,
                            user_id=identity.user_id, role_id=role.id, status="active", joined_at=now,
                        )
                        self._repo.add(membership)
                        self._repo.add(CustomerRelationship(
                            organization_id=organization.id, user_id=identity.user_id,
                            display_name=identity.user.display_name,
                        ))
                        self._session.flush()
                        self._audit.record("auth.customer_relationship_created", "success", organization_id=organization.id, actor_user_id=identity.user_id)
                logger.warning(
                    "customer_login_membership_lookup outcome=%s membership_active=%s",
                    "found" if membership is not None else "not_found",
                    membership is not None,
                )
                if membership is None:
                    raise MembershipInactive("An active JDS membership is required.")
                self.login_stage = "role_resolution"
                role = self._session.get(Role, membership.role_id)
                logger.warning(
                    "customer_login_role_resolved role=%s",
                    role.key if role is not None else "not_found",
                )
                if role is None or (allowed_roles is not None and role.key not in allowed_roles):
                    raise MembershipInactive("This account is not authorized for this experience.")
                self.login_stage = "session_issuance"
                email_local_part = authentication.identity.email.split("@", 1)[0].strip()
                if (
                    authentication.identity.display_name
                    and identity.user.display_name.casefold() == email_local_part.casefold()
                ):
                    identity.user.display_name = authentication.identity.display_name
                identity.user.last_authenticated_at = now
                identity.user.email_verified_at = identity.user.email_verified_at or now
                identity.provider_email = authentication.identity.email
                issued = self._issue(identity.user, membership, authentication, now, user_agent, persistent)
                self._audit.record("auth.login", "success", organization_id=organization.id, actor_user_id=identity.user_id, session_id=issued.principal.session_id)
        except Exception:
            logger.warning("customer_login_failed stage=%s", self.login_stage)
            raise
        self.login_stage = "complete"
        logger.warning("customer_login_completed")
        return issued

    def register_customer(self, email: str, password: str, display_name: str, phone: str, *, now: datetime) -> None:
        normalized = email.strip().lower()
        self.registration_stage = "supabase_registration"
        identity = self._provider.register_user(
            normalized, password,
            f"{self._settings.frontend_url.rstrip('/')}/account/verify-email",
        )
        with self._session.begin():
            self.registration_stage = "application_lookup"
            application = self._repo.application_by_key(self._settings.application_key)
            if application is None:
                raise CustomerRegistrationError(
                    "Customer authorization is unavailable.",
                    stage="application_lookup",
                    reason="missing_application",
                )
            if not application.is_active:
                raise CustomerRegistrationError(
                    "Customer authorization is unavailable.",
                    stage="application_lookup",
                    reason="inactive_application",
                )
            self.registration_stage = "organization_lookup"
            organization = self._session.get(Organization, self._organization_id) if self._organization_id else self._repo.organization_by_slug(self._settings.organization_slug)
            if organization is None:
                raise CustomerRegistrationError(
                    "Customer authorization is unavailable.",
                    stage="organization_lookup",
                    reason="missing_organization",
                )
            if not organization.is_active:
                raise CustomerRegistrationError(
                    "Customer authorization is unavailable.",
                    stage="organization_lookup",
                    reason="inactive_organization",
                )
            self.registration_stage = "customer_role_lookup"
            role = self._repo.role_by_key(application.id, "customer")
            if role is None:
                raise CustomerRegistrationError(
                    "Customer authorization is unavailable.",
                    stage="customer_role_lookup",
                    reason="missing_customer_role",
                )
            self.registration_stage = "external_identity_lookup"
            if self._repo.identity(identity.issuer, identity.subject) is not None:
                raise CustomerRegistrationError(
                    "Account already exists.",
                    stage="external_identity_lookup",
                    reason="duplicate_external_identity",
                )
            self.registration_stage = "jds_user_creation"
            user = JdsUser(
                primary_email=identity.email, display_name=display_name.strip(), status="active",
                email_verified_at=now if identity.email_verified else None,
            )
            self._repo.add(user)
            self._session.flush()
            self._repo.add(CustomerRelationship(organization_id=organization.id, user_id=user.id, display_name=display_name.strip(), phone=phone))
            self.registration_stage = "external_identity_creation"
            self._repo.add(ExternalIdentity(
                user_id=user.id, issuer=identity.issuer, subject=identity.subject,
                provider="supabase", provider_email=identity.email,
            ))
            self._session.flush()
            self.registration_stage = "membership_creation"
            self._repo.add(Membership(
                organization_id=organization.id, application_id=application.id,
                user_id=user.id, role_id=role.id, status="active", joined_at=now,
            ))
            self._session.flush()
            self.registration_stage = "audit_recording"
            self._audit.record("auth.customer_registered", "success", organization_id=organization.id, actor_user_id=user.id)

    def verify_customer_email(self, token_hash: str, *, now: datetime) -> None:
        self.verification_stage = "supabase_verification"
        authentication = self._provider.verify_email_token(token_hash, "email")
        with self._session.begin():
            self.verification_stage = "external_identity_lookup"
            identity = self._repo.identity(authentication.identity.issuer, authentication.identity.subject)
            if identity is None:
                raise CustomerVerificationError(
                    "Registration could not be verified.",
                    stage="external_identity_lookup",
                    reason="missing_external_identity",
                )
            self.verification_stage = "application_lookup"
            application = self._repo.application_by_key(self._settings.application_key)
            if application is None:
                raise CustomerVerificationError(
                    "Customer membership is unavailable.",
                    stage="application_lookup",
                    reason="missing_application",
                )
            if not application.is_active:
                raise CustomerVerificationError(
                    "Customer membership is unavailable.",
                    stage="application_lookup",
                    reason="inactive_application",
                )
            self.verification_stage = "organization_lookup"
            organization = self._repo.organization_by_slug(self._settings.organization_slug)
            if organization is None:
                raise CustomerVerificationError(
                    "Customer membership is unavailable.",
                    stage="organization_lookup",
                    reason="missing_organization",
                )
            if not organization.is_active:
                raise CustomerVerificationError(
                    "Customer membership is unavailable.",
                    stage="organization_lookup",
                    reason="inactive_organization",
                )
            self.verification_stage = "membership_lookup"
            membership = self._repo.active_membership(
                identity.user_id,
                application.id,
                organization.id,
            )
            if membership is None:
                raise CustomerVerificationError(
                    "Customer membership is required.",
                    stage="membership_lookup",
                    reason="missing_active_membership",
                )
            self.verification_stage = "customer_role_lookup"
            role = self._session.get(Role, membership.role_id)
            if role is None:
                raise CustomerVerificationError(
                    "Customer membership is required.",
                    stage="customer_role_lookup",
                    reason="missing_role",
                )
            if role.key != "customer":
                raise CustomerVerificationError(
                    "Customer membership is required.",
                    stage="customer_role_lookup",
                    reason="non_customer_role",
                )
            self.verification_stage = "verification_persistence"
            identity.user.email_verified_at = now
            identity.provider_email = authentication.identity.email
            self._audit.record("auth.customer_email_verified", "success", organization_id=membership.organization_id, actor_user_id=identity.user_id)

    def resend_customer_verification(self, email: str) -> None:
        self._provider.resend_verification(
            email.strip().lower(),
            f"{self._settings.frontend_url.rstrip('/')}/account/verify-email",
        )

    def resolve(self, token: str, *, now: datetime, touch: bool = True) -> AuthPrincipal:
        token_hash = hash_secret(token, self._settings.session_pepper)
        owner_session = self._repo.session_by_hash(token_hash)
        if owner_session is None or owner_session.revoked_at is not None or owner_session.idle_expires_at <= now or owner_session.absolute_expires_at <= now:
            raise SessionInvalid("Session is invalid or expired.")
        identity_user = self._session.get(JdsUser, owner_session.user_id)
        membership = self._session.get(Membership, owner_session.membership_id)
        if (
            identity_user is None
            or identity_user.status != "active"
            or identity_user.credential_state != "active"
            or membership is None
            or membership.status != "active"
            or membership.user_id != owner_session.user_id
            or membership.organization_id != owner_session.organization_id
            or membership.application_id != owner_session.application_id
            or owner_session.security_version != identity_user.security_version
        ):
            raise SessionInvalid("Session is no longer authorized.")
        role = self._session.get(Role, membership.role_id)
        organization = self._session.get(Organization, membership.organization_id)
        application = self._session.get(JdsApplication, membership.application_id)
        if role is None or organization is None or not organization.is_active or application is None or not application.is_active:
            raise SessionInvalid("Session is no longer authorized.")
        if touch:
            owner_session.last_seen_at = now
            idle_lifetime = (
                timedelta(days=self._settings.customer_persistent_session_days)
                if owner_session.is_persistent
                else timedelta(minutes=self._settings.session_idle_minutes)
            )
            owner_session.idle_expires_at = min(now + idle_lifetime, owner_session.absolute_expires_at)
        return AuthPrincipal(identity_user.id, membership.id, membership.organization_id, membership.application_id, owner_session.id, identity_user.primary_email, identity_user.display_name, role.key, self._repo.permissions_for_role(role.id), owner_session.assurance_level)

    def rotate_csrf(self, token: str, *, now: datetime) -> tuple[AuthPrincipal, str]:
        with self._session.begin():
            principal = self.resolve(token, now=now)
            csrf = create_secret()
            owner_session = self._session.get(OwnerSession, principal.session_id)
            assert owner_session is not None
            owner_session.csrf_token_hash = hash_secret(csrf, self._settings.session_pepper)
        return principal, csrf

    def verify_csrf(self, principal: AuthPrincipal, csrf_token: str) -> None:
        owner_session = self._session.get(OwnerSession, principal.session_id)
        if owner_session is None or not secret_matches(csrf_token, owner_session.csrf_token_hash, self._settings.session_pepper):
            raise CsrfInvalid("CSRF validation failed.")

    def logout(self, principal: AuthPrincipal, *, now: datetime) -> None:
        with self._session.begin():
            owner_session = self._session.get(OwnerSession, principal.session_id)
            if owner_session is not None and owner_session.revoked_at is None:
                owner_session.revoked_at = now
                owner_session.revocation_reason = "logout"
            self._audit.record("auth.logout", "success", organization_id=principal.organization_id, actor_user_id=principal.user_id, session_id=principal.session_id)

    def request_password_reset(self, email: str, redirect_url: str) -> None:
        self._provider.request_password_reset(email.strip().lower(), redirect_url)

    def complete_password_reset(self, token_hash: str | None, password: str, *, access_token: str | None = None, now: datetime) -> None:
        recovery_method = "access_token" if access_token else "token_hash"
        logger.warning(
            "customer_password_reset_started recovery_method=%s",
            recovery_method,
        )
        self.password_reset_stage = "recovery_session_validation" if access_token else "recovery_token_verification"
        try:
            authentication = (
                self._provider.authenticate_access_token(access_token)
                if access_token
                else self._provider.verify_email_token(token_hash or "", "recovery")
            )
        except Exception:
            logger.warning(
                "customer_password_reset_credential_failed recovery_method=%s stage=%s",
                recovery_method,
                self.password_reset_stage,
            )
            raise
        logger.warning(
            "customer_password_reset_credential_succeeded recovery_method=%s stage=%s",
            recovery_method,
            self.password_reset_stage,
        )
        with self._session.begin():
            self.password_reset_stage = "identity_lookup"
            try:
                identity = self._repo.identity(authentication.identity.issuer, authentication.identity.subject)
                if identity is None:
                    identity = self._reconcile_orphaned_customer(authentication, now)
                if identity.user.status != "active":
                    raise MembershipInactive("An active JDS identity is required.")
            except Exception:
                logger.warning("customer_password_reset_identity_failed stage=%s", self.password_reset_stage)
                raise
            logger.warning("customer_password_reset_identity_resolved stage=%s", self.password_reset_stage)
            self.password_reset_stage = "recovery_pending_persistence"
            identity.user.security_version += 1
            identity.user.credential_state = "recovery_pending"
            identity.user.recovery_started_at = now
            self._repo.revoke_user_sessions(identity.user_id, now, "password_reset_pending")
            user_id = identity.user_id
        self.password_reset_stage = "supabase_password_update"
        try:
            self._provider.update_password(authentication.access_token, password)
        except Exception:
            logger.warning("customer_password_reset_password_update_failed stage=%s", self.password_reset_stage)
            raise
        logger.warning("customer_password_reset_password_update_succeeded stage=%s", self.password_reset_stage)
        with self._session.begin():
            self.password_reset_stage = "recovery_completion_persistence"
            user = self._session.get(JdsUser, user_id, with_for_update=True)
            if user is None:
                raise MembershipInactive("An active JDS identity is required.")
            user.credential_state = "active"
            user.recovery_started_at = None
            self._repo.revoke_user_sessions(user.id, now, "password_reset")
            self._audit.record("auth.password_reset", "success", actor_user_id=user.id)

    def _reconcile_orphaned_customer(self, authentication: ProviderAuthentication, now: datetime) -> ExternalIdentity:
        if not authentication.identity.email_verified:
            raise MembershipInactive("A verified JDS identity is required.")
        application, organization = self._scope()
        role = self._repo.role_by_key(application.id, "customer")
        if role is None or self._repo.user_by_email(authentication.identity.email) is not None:
            raise MembershipInactive("An active JDS identity is required.")
        display_name = authentication.identity.display_name or "Customer"
        user = JdsUser(
            primary_email=authentication.identity.email,
            display_name=display_name,
            status="active",
            email_verified_at=now,
        )
        self._repo.add(user)
        self._session.flush()
        identity = ExternalIdentity(
            user_id=user.id,
            issuer=authentication.identity.issuer,
            subject=authentication.identity.subject,
            provider="supabase",
            provider_email=authentication.identity.email,
        )
        self._repo.add(identity)
        self._repo.add(Membership(
            organization_id=organization.id,
            application_id=application.id,
            user_id=user.id,
            role_id=role.id,
            status="active",
            joined_at=now,
        ))
        self._session.flush()
        self._audit.record(
            "auth.customer_reconciled",
            "success",
            organization_id=organization.id,
            actor_user_id=user.id,
        )
        return identity

    def logout_all(self, principal: AuthPrincipal, *, now: datetime) -> None:
        with self._session.begin():
            user = self._session.get(JdsUser, principal.user_id, with_for_update=True)
            if user is None:
                raise SessionInvalid("Session is no longer authorized.")
            user.security_version += 1
            self._repo.revoke_user_sessions(user.id, now, "logout_all")
            self._audit.record(
                "auth.logout_all",
                "success",
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                session_id=principal.session_id,
            )

    def workforce_organizations(self, principal: AuthPrincipal) -> list[tuple[Membership, Organization, Role]]:
        rows: list[tuple[Membership, Organization, Role]] = []
        for membership in self._repo.active_workforce_memberships(principal.user_id, principal.application_id):
            organization = self._session.get(Organization, membership.organization_id)
            role = self._session.get(Role, membership.role_id)
            if organization is not None and role is not None:
                rows.append((membership, organization, role))
        return rows

    def switch_membership(self, principal: AuthPrincipal, membership_id: UUID, *, now: datetime, user_agent: str | None) -> IssuedSession:
        with self._session.begin():
            membership = next(
                (item for item in self._repo.active_workforce_memberships(principal.user_id, principal.application_id) if item.id == membership_id),
                None,
            )
            user = self._session.get(JdsUser, principal.user_id)
            current = self._session.get(OwnerSession, principal.session_id, with_for_update=True)
            if membership is None or user is None or current is None or current.revoked_at is not None:
                raise MembershipInactive("The selected organization membership is unavailable.")
            authentication = ProviderAuthentication(
                ProviderIdentity(
                    "jds-session", str(user.id), user.primary_email, True,
                    principal.assurance_level, user.display_name,
                ),
                "",
            )
            issued = self._issue(user, membership, authentication, now, user_agent, False)
            current.revoked_at = now
            current.revocation_reason = "membership_switched"
            self._audit.record("auth.membership_selected", "success", organization_id=membership.organization_id, actor_user_id=user.id, session_id=issued.principal.session_id, target_type="membership", target_id=str(membership.id))
            return issued

    def create_invitation(self, email: str, role_key: str, *, now: datetime, invited_by: AuthPrincipal | None) -> OwnerInvitation:
        normalized = email.strip().lower()
        invitation_secret = create_secret()
        with self._session.begin():
            if invited_by is None:
                application, organization = self._scope()
            else:
                membership = self._repo.active_membership(
                    invited_by.user_id, invited_by.application_id,
                    invited_by.organization_id,
                )
                application = self._session.get(JdsApplication, invited_by.application_id)
                organization = self._session.get(Organization, invited_by.organization_id)
                if (
                    membership is None or membership.id != invited_by.membership_id
                    or application is None or not application.is_active
                    or organization is None or not organization.is_active
                ):
                    raise MembershipInactive("The inviting membership is unavailable.")
            role = self._repo.role_by_key(application.id, role_key)
            if role is None:
                raise ValueError("Unknown role.")
            invitation = OwnerInvitation(organization_id=organization.id, application_id=application.id, role_id=role.id, email=normalized, secret_hash=hash_secret(invitation_secret, self._settings.session_pepper), invited_by_membership_id=invited_by.membership_id if invited_by else None, expires_at=now + timedelta(hours=24))
            self._repo.add(invitation)
            self._session.flush()
        try:
            provider_subject = self._provider.invite_user(
                normalized,
                f"{self._settings.frontend_url.rstrip('/')}/admin/invitation?{urlencode({'invitation_id': str(invitation.id), 'invitation_secret': invitation_secret})}",
            )
        except Exception:
            with self._session.begin():
                invitation.status = "delivery_failed"
            raise
        with self._session.begin():
            invitation.provider_subject = provider_subject
            invitation.status = "sent"
            self._audit.record("auth.invitation_created", "success", organization_id=organization.id, actor_user_id=invited_by.user_id if invited_by else None, target_type="invitation", target_id=str(invitation.id))
        return invitation

    def accept_invitation(self, invitation_id: UUID, invitation_secret: str, token_hash: str, password: str, display_name: str, *, now: datetime) -> None:
        authentication = self._provider.verify_email_token(token_hash, "invite")
        if not authentication.identity.email_verified:
            raise EmailVerificationRequired("Email verification is required.")
        with self._session.begin():
            application, organization = self._scope()
            invitation = self._repo.invitation_for_update(invitation_id)
            if not self._invitation_matches(invitation, invitation_secret, authentication, application.id, organization.id, now, "sent"):
                raise InvitationInvalid("A valid invitation is required.")
            invitation.status = "accepting"
        try:
            self._provider.update_password(authentication.access_token, password)
        except Exception:
            with self._session.begin():
                invitation = self._repo.invitation_for_update(invitation_id)
                if invitation is not None and invitation.status == "accepting":
                    invitation.status = "sent"
            raise
        with self._session.begin():
            application, organization = self._scope()
            invitation = self._repo.invitation_for_update(invitation_id)
            if not self._invitation_matches(invitation, invitation_secret, authentication, application.id, organization.id, now, "accepting"):
                raise InvitationInvalid("A valid invitation is required.")
            assert invitation is not None
            user = JdsUser(primary_email=authentication.identity.email, display_name=display_name.strip(), status="active", email_verified_at=now)
            self._repo.add(user)
            self._session.flush()
            self._repo.add(ExternalIdentity(user_id=user.id, issuer=authentication.identity.issuer, subject=authentication.identity.subject, provider="supabase", provider_email=authentication.identity.email))
            self._repo.add(Membership(organization_id=organization.id, application_id=application.id, user_id=user.id, role_id=invitation.role_id, status="active", joined_at=now))
            invitation.status = "accepted"
            invitation.accepted_at = now
            invitation.provider_subject = authentication.identity.subject
            self._audit.record("auth.invitation_accepted", "success", organization_id=organization.id, actor_user_id=user.id, target_type="invitation", target_id=str(invitation.id))

    def _invitation_matches(self, invitation: OwnerInvitation | None, secret: str, authentication: ProviderAuthentication, application_id: UUID, organization_id: UUID, now: datetime, status: str) -> bool:
        return bool(
            invitation is not None
            and invitation.status == status
            and invitation.expires_at > now
            and invitation.application_id == application_id
            and invitation.organization_id == organization_id
            and invitation.provider_subject == authentication.identity.subject
            and invitation.email == authentication.identity.email.strip().lower()
            and secret_matches(secret, invitation.secret_hash, self._settings.session_pepper)
        )

    def _scope(self):
        application = self._repo.application_by_key(self._settings.application_key)
        organization = self._session.get(Organization, self._organization_id) if self._organization_id else self._repo.organization_by_slug(self._settings.organization_slug)
        if application is None or organization is None or not application.is_active or not organization.is_active:
            raise MembershipInactive("JDS authentication scope is unavailable.")
        return application, organization

    def _scope_ids(self) -> tuple[UUID, UUID]:
        application, organization = self._scope()
        return application.id, organization.id

    def _issue(self, user: JdsUser, membership: Membership, authentication: ProviderAuthentication, now: datetime, user_agent: str | None, persistent: bool) -> IssuedSession:
        token, csrf = create_secret(), create_secret()
        absolute_lifetime = (
            timedelta(days=self._settings.customer_persistent_session_days)
            if persistent
            else timedelta(hours=self._settings.session_absolute_hours)
        )
        idle_lifetime = (
            timedelta(days=self._settings.customer_persistent_session_days)
            if persistent
            else timedelta(minutes=self._settings.session_idle_minutes)
        )
        absolute = now + absolute_lifetime
        owner_session = OwnerSession(token_hash=hash_secret(token, self._settings.session_pepper), csrf_token_hash=hash_secret(csrf, self._settings.session_pepper), user_id=user.id, membership_id=membership.id, organization_id=membership.organization_id, application_id=membership.application_id, assurance_level=authentication.identity.assurance_level, security_version=user.security_version, is_persistent=persistent, authenticated_at=now, last_seen_at=now, idle_expires_at=min(now + idle_lifetime, absolute), absolute_expires_at=absolute, user_agent=(user_agent or "")[:500] or None)
        self._repo.add(owner_session)
        self._session.flush()
        role = self._session.get(Role, membership.role_id)
        assert role is not None
        principal = AuthPrincipal(user.id, membership.id, membership.organization_id, membership.application_id, owner_session.id, user.primary_email, user.display_name, role.key, self._repo.permissions_for_role(role.id), owner_session.assurance_level)
        return IssuedSession(token, csrf, principal, absolute)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
