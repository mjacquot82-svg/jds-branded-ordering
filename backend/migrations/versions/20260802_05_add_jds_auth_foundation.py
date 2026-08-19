"""add reusable JDS authentication foundation

Revision ID: 20260802_05
Revises: 20260729_04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_05"
down_revision: str | None = "20260729_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), nullable=False)


def upgrade() -> None:
    op.create_table("jds_applications", uuid_pk(), sa.Column("key", sa.String(100), nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False), *timestamps(), sa.PrimaryKeyConstraint("id", name="pk_jds_applications"), sa.UniqueConstraint("key", name="uq_jds_applications_key"))
    op.create_table("organizations", uuid_pk(), sa.Column("slug", sa.String(100), nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False), *timestamps(), sa.PrimaryKeyConstraint("id", name="pk_organizations"), sa.UniqueConstraint("slug", name="uq_organizations_slug"))
    op.create_table("jds_users", uuid_pk(), sa.Column("primary_email", sa.String(320), nullable=False), sa.Column("display_name", sa.String(200), nullable=False), sa.Column("status", sa.String(20), server_default="active", nullable=False), sa.Column("email_verified_at", sa.DateTime(timezone=True)), sa.Column("last_authenticated_at", sa.DateTime(timezone=True)), *timestamps(), sa.CheckConstraint("status IN ('active', 'suspended', 'disabled')", name="ck_jds_users_status_valid"), sa.PrimaryKeyConstraint("id", name="pk_jds_users"), sa.UniqueConstraint("primary_email", name="uq_jds_users_primary_email"))
    op.create_table("auth_permissions", uuid_pk(), sa.Column("application_id", sa.Uuid(), nullable=False), sa.Column("key", sa.String(100), nullable=False), sa.Column("description", sa.String(500), nullable=False), *timestamps(), sa.ForeignKeyConstraint(["application_id"], ["jds_applications.id"], name="fk_auth_permissions_application_id_jds_applications", ondelete="CASCADE"), sa.PrimaryKeyConstraint("id", name="pk_auth_permissions"), sa.UniqueConstraint("application_id", "key", name="uq_auth_permissions_application_key"))
    op.create_index("ix_auth_permissions_application_id", "auth_permissions", ["application_id"])
    op.create_table("auth_roles", uuid_pk(), sa.Column("application_id", sa.Uuid(), nullable=False), sa.Column("key", sa.String(100), nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("is_system", sa.Boolean(), server_default="true", nullable=False), *timestamps(), sa.ForeignKeyConstraint(["application_id"], ["jds_applications.id"], name="fk_auth_roles_application_id_jds_applications", ondelete="CASCADE"), sa.PrimaryKeyConstraint("id", name="pk_auth_roles"), sa.UniqueConstraint("application_id", "key", name="uq_auth_roles_application_key"))
    op.create_index("ix_auth_roles_application_id", "auth_roles", ["application_id"])
    op.create_table("external_identities", uuid_pk(), sa.Column("user_id", sa.Uuid(), nullable=False), sa.Column("issuer", sa.String(500), nullable=False), sa.Column("subject", sa.String(200), nullable=False), sa.Column("provider", sa.String(50), nullable=False), sa.Column("provider_email", sa.String(320), nullable=False), *timestamps(), sa.ForeignKeyConstraint(["user_id"], ["jds_users.id"], name="fk_external_identities_user_id_jds_users", ondelete="CASCADE"), sa.PrimaryKeyConstraint("id", name="pk_external_identities"), sa.UniqueConstraint("issuer", "subject", name="uq_external_identities_issuer_subject"))
    op.create_index("ix_external_identities_user_id", "external_identities", ["user_id"])
    op.create_table("auth_role_permissions", sa.Column("role_id", sa.Uuid(), nullable=False), sa.Column("permission_id", sa.Uuid(), nullable=False), sa.ForeignKeyConstraint(["permission_id"], ["auth_permissions.id"], name="fk_auth_role_permissions_permission_id_auth_permissions", ondelete="CASCADE"), sa.ForeignKeyConstraint(["role_id"], ["auth_roles.id"], name="fk_auth_role_permissions_role_id_auth_roles", ondelete="CASCADE"), sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_auth_role_permissions"))
    op.create_table("organization_memberships", uuid_pk(), sa.Column("organization_id", sa.Uuid(), nullable=False), sa.Column("application_id", sa.Uuid(), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False), sa.Column("role_id", sa.Uuid(), nullable=False), sa.Column("status", sa.String(20), server_default="invited", nullable=False), sa.Column("joined_at", sa.DateTime(timezone=True)), *timestamps(), sa.CheckConstraint("status IN ('invited', 'active', 'suspended', 'revoked')", name="ck_organization_memberships_status_valid"), sa.ForeignKeyConstraint(["application_id"], ["jds_applications.id"], name="fk_organization_memberships_application_id_jds_applications", ondelete="CASCADE"), sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_organization_memberships_organization_id_organizations", ondelete="CASCADE"), sa.ForeignKeyConstraint(["role_id"], ["auth_roles.id"], name="fk_organization_memberships_role_id_auth_roles", ondelete="RESTRICT"), sa.ForeignKeyConstraint(["user_id"], ["jds_users.id"], name="fk_organization_memberships_user_id_jds_users", ondelete="CASCADE"), sa.PrimaryKeyConstraint("id", name="pk_organization_memberships"), sa.UniqueConstraint("organization_id", "application_id", "user_id", name="uq_memberships_org_app_user"))
    for column in ("organization_id", "application_id", "user_id"):
        op.create_index(f"ix_organization_memberships_{column}", "organization_memberships", [column])
    op.create_table("owner_invitations", uuid_pk(), sa.Column("organization_id", sa.Uuid(), nullable=False), sa.Column("application_id", sa.Uuid(), nullable=False), sa.Column("role_id", sa.Uuid(), nullable=False), sa.Column("email", sa.String(320), nullable=False), sa.Column("status", sa.String(30), server_default="pending_delivery", nullable=False), sa.Column("provider_subject", sa.String(200)), sa.Column("invited_by_membership_id", sa.Uuid()), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("accepted_at", sa.DateTime(timezone=True)), *timestamps(), sa.CheckConstraint("status IN ('pending_delivery', 'sent', 'accepted', 'revoked', 'expired', 'delivery_failed')", name="ck_owner_invitations_status_valid"), sa.ForeignKeyConstraint(["application_id"], ["jds_applications.id"], name="fk_owner_invitations_application_id_jds_applications", ondelete="CASCADE"), sa.ForeignKeyConstraint(["invited_by_membership_id"], ["organization_memberships.id"], name="fk_owner_invites_inviter_membership", ondelete="SET NULL"), sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_owner_invitations_organization_id_organizations", ondelete="CASCADE"), sa.ForeignKeyConstraint(["role_id"], ["auth_roles.id"], name="fk_owner_invitations_role_id_auth_roles", ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id", name="pk_owner_invitations"))
    for column in ("organization_id", "application_id", "email", "expires_at"):
        op.create_index(f"ix_owner_invitations_{column}", "owner_invitations", [column])
    op.create_table("owner_sessions", uuid_pk(), sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("csrf_token_hash", sa.String(64), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False), sa.Column("membership_id", sa.Uuid(), nullable=False), sa.Column("organization_id", sa.Uuid(), nullable=False), sa.Column("application_id", sa.Uuid(), nullable=False), sa.Column("assurance_level", sa.String(20), server_default="aal1", nullable=False), sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False), sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("revoked_at", sa.DateTime(timezone=True)), sa.Column("revocation_reason", sa.String(200)), sa.Column("user_agent", sa.String(500)), *timestamps(), sa.ForeignKeyConstraint(["application_id"], ["jds_applications.id"], name="fk_owner_sessions_application_id_jds_applications", ondelete="CASCADE"), sa.ForeignKeyConstraint(["membership_id"], ["organization_memberships.id"], name="fk_owner_sessions_membership_id_organization_memberships", ondelete="CASCADE"), sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_owner_sessions_organization_id_organizations", ondelete="CASCADE"), sa.ForeignKeyConstraint(["user_id"], ["jds_users.id"], name="fk_owner_sessions_user_id_jds_users", ondelete="CASCADE"), sa.PrimaryKeyConstraint("id", name="pk_owner_sessions"), sa.UniqueConstraint("token_hash", name="uq_owner_sessions_token_hash"))
    for column in ("user_id", "membership_id", "organization_id", "application_id", "idle_expires_at", "absolute_expires_at"):
        op.create_index(f"ix_owner_sessions_{column}", "owner_sessions", [column])
    op.create_table("security_audit_events", uuid_pk(), sa.Column("organization_id", sa.Uuid()), sa.Column("actor_user_id", sa.Uuid()), sa.Column("session_id", sa.Uuid()), sa.Column("action", sa.String(100), nullable=False), sa.Column("target_type", sa.String(100)), sa.Column("target_id", sa.String(200)), sa.Column("outcome", sa.String(30), nullable=False), sa.Column("details", sa.Text()), sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.ForeignKeyConstraint(["actor_user_id"], ["jds_users.id"], name="fk_security_audit_events_actor_user_id_jds_users", ondelete="SET NULL"), sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_security_audit_events_organization_id_organizations", ondelete="SET NULL"), sa.ForeignKeyConstraint(["session_id"], ["owner_sessions.id"], name="fk_security_audit_events_session_id_owner_sessions", ondelete="SET NULL"), sa.PrimaryKeyConstraint("id", name="pk_security_audit_events"))
    for column in ("organization_id", "actor_user_id", "action", "occurred_at"):
        op.create_index(f"ix_security_audit_events_{column}", "security_audit_events", [column])


def downgrade() -> None:
    for table in ("security_audit_events", "owner_sessions", "owner_invitations", "organization_memberships", "auth_role_permissions", "external_identities", "auth_roles", "auth_permissions", "jds_users", "organizations", "jds_applications"):
        op.drop_table(table)
