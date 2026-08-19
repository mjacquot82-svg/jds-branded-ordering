from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jds_auth.models import (
    ExternalIdentity,
    JdsApplication,
    JdsUser,
    Membership,
    Organization,
    OwnerInvitation,
    OwnerSession,
    Permission,
    Role,
    RolePermission,
)


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: object) -> None:
        self.session.add(entity)

    def application_by_key(self, key: str) -> JdsApplication | None:
        return self.session.scalar(select(JdsApplication).where(JdsApplication.key == key))

    def organization_by_slug(self, slug: str) -> Organization | None:
        return self.session.scalar(select(Organization).where(Organization.slug == slug))

    def role_by_key(self, application_id: UUID, key: str) -> Role | None:
        return self.session.scalar(select(Role).where(Role.application_id == application_id, Role.key == key))

    def identity(self, issuer: str, subject: str) -> ExternalIdentity | None:
        return self.session.scalar(select(ExternalIdentity).where(ExternalIdentity.issuer == issuer, ExternalIdentity.subject == subject))

    def user_by_email(self, email: str) -> JdsUser | None:
        return self.session.scalar(select(JdsUser).where(JdsUser.primary_email == email))

    def active_membership(self, user_id: UUID, application_id: UUID, organization_id: UUID) -> Membership | None:
        return self.session.scalar(select(Membership).where(Membership.user_id == user_id, Membership.application_id == application_id, Membership.organization_id == organization_id, Membership.status == "active"))

    def active_workforce_memberships(self, user_id: UUID, application_id: UUID) -> list[Membership]:
        return list(self.session.scalars(
            select(Membership)
            .join(Role, Role.id == Membership.role_id)
            .join(Organization, Organization.id == Membership.organization_id)
            .where(
                Membership.user_id == user_id,
                Membership.application_id == application_id,
                Membership.status == "active",
                Role.key.in_(("owner", "manager", "staff")),
                Organization.is_active.is_(True),
            )
            .order_by(Organization.name, Membership.id)
        ))

    def invitation_for_update(self, invitation_id: UUID) -> OwnerInvitation | None:
        return self.session.scalar(
            select(OwnerInvitation)
            .where(OwnerInvitation.id == invitation_id)
            .with_for_update()
        )

    def session_by_hash(self, token_hash: str) -> OwnerSession | None:
        return self.session.scalar(select(OwnerSession).where(OwnerSession.token_hash == token_hash))

    def permissions_for_role(self, role_id: UUID) -> frozenset[str]:
        return frozenset(self.session.scalars(select(Permission.key).join(RolePermission, Permission.id == RolePermission.permission_id).where(RolePermission.role_id == role_id)).all())

    def revoke_user_sessions(self, user_id: UUID, now: datetime, reason: str) -> None:
        for owner_session in self.session.scalars(select(OwnerSession).where(OwnerSession.user_id == user_id, OwnerSession.revoked_at.is_(None))):
            owner_session.revoked_at = now
            owner_session.revocation_reason = reason
