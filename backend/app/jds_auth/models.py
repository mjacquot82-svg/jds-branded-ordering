from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class JdsApplication(Timestamped, Base):
    __tablename__ = "jds_applications"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Organization(Timestamped, Base):
    __tablename__ = "organizations"
    __table_args__ = (CheckConstraint("lifecycle_status IN ('onboarding','active','suspended','archived')", name="lifecycle_status"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    lifecycle_status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")


class JdsUser(Timestamped, Base):
    __tablename__ = "jds_users"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended', 'disabled')", name="status_valid"),
        CheckConstraint("credential_state IN ('active', 'recovery_pending')", name="credential_state_valid"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    primary_email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    security_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    credential_state: Mapped[str] = mapped_column(String(30), default="active", server_default="active")
    recovery_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_authenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExternalIdentity(Timestamped, Base):
    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_external_identities_issuer_subject"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("jds_users.id", ondelete="CASCADE"), index=True)
    issuer: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(50))
    provider_email: Mapped[str] = mapped_column(String(320))
    user: Mapped[JdsUser] = relationship()


class StaffPinCredential(Timestamped, Base):
    __tablename__ = "staff_pin_credentials"
    membership_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization_memberships.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("jds_users.id", ondelete="CASCADE"), index=True)
    verifier: Mapped[str] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Role(Timestamped, Base):
    __tablename__ = "auth_roles"
    __table_args__ = (UniqueConstraint("application_id", "key", name="uq_auth_roles_application_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("jds_applications.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Permission(Timestamped, Base):
    __tablename__ = "auth_permissions"
    __table_args__ = (UniqueConstraint("application_id", "key", name="uq_auth_permissions_application_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("jds_applications.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))


class RolePermission(Base):
    __tablename__ = "auth_role_permissions"
    role_id: Mapped[UUID] = mapped_column(ForeignKey("auth_roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[UUID] = mapped_column(ForeignKey("auth_permissions.id", ondelete="CASCADE"), primary_key=True)


class Membership(Timestamped, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "application_id", "user_id", name="uq_memberships_org_app_user"),
        UniqueConstraint("id", "user_id", "organization_id", "application_id", name="uq_memberships_id_user_org_app"),
        CheckConstraint("status IN ('invited', 'active', 'suspended', 'revoked')", name="status_valid"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("jds_applications.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("jds_users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("auth_roles.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), default="invited", server_default="invited")
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OwnerSession(Timestamped, Base):
    __tablename__ = "owner_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["membership_id", "user_id", "organization_id", "application_id"],
            ["organization_memberships.id", "organization_memberships.user_id", "organization_memberships.organization_id", "organization_memberships.application_id"],
            name="fk_owner_sessions_membership_scope", ondelete="CASCADE",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("jds_users.id", ondelete="CASCADE"), index=True)
    membership_id: Mapped[UUID] = mapped_column(index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("jds_applications.id", ondelete="CASCADE"), index=True)
    assurance_level: Mapped[str] = mapped_column(String(20), default="aal1", server_default="aal1")
    security_version: Mapped[int] = mapped_column(Integer)
    is_persistent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(String(200))
    user_agent: Mapped[str | None] = mapped_column(String(500))


class OwnerInvitation(Timestamped, Base):
    __tablename__ = "owner_invitations"
    __table_args__ = (
        CheckConstraint("status IN ('pending_delivery', 'sent', 'accepting', 'accepted', 'revoked', 'expired', 'delivery_failed')", name="status_valid"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("jds_applications.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("auth_roles.id", ondelete="RESTRICT"))
    email: Mapped[str] = mapped_column(String(320), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_delivery", server_default="pending_delivery")
    provider_subject: Mapped[str | None] = mapped_column(String(200))
    secret_hash: Mapped[str] = mapped_column(String(64))
    invited_by_membership_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "organization_memberships.id",
            name="fk_owner_invites_inviter_membership",
            ondelete="SET NULL",
        )
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthRateLimitBucket(Base):
    __tablename__ = "auth_rate_limit_buckets"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    lock_key: Mapped[int] = mapped_column(BigInteger)


class SecurityAuditEvent(Base):
    __tablename__ = "security_audit_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("jds_users.id", ondelete="SET NULL"), index=True)
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("owner_sessions.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str | None] = mapped_column(String(100))
    target_id: Mapped[str | None] = mapped_column(String(200))
    outcome: Mapped[str] = mapped_column(String(30))
    details: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
