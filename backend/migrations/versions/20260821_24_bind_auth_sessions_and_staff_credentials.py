"""Bind authentication sessions and staff PINs to memberships.

Revision ID: 20260821_24
Revises: 20260820_23
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_24"
down_revision: str | None = "20260820_23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("staff_pin_credentials", sa.Column("membership_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE staff_pin_credentials credential
        SET membership_id = membership.id
        FROM organization_memberships membership
        JOIN auth_roles role ON role.id = membership.role_id
        WHERE membership.user_id = credential.user_id
          AND membership.status = 'active'
          AND role.key = 'staff'
          AND NOT EXISTS (
              SELECT 1 FROM organization_memberships other
              JOIN auth_roles other_role ON other_role.id = other.role_id
              WHERE other.user_id = credential.user_id
                AND other.status = 'active'
                AND other_role.key = 'staff'
                AND other.id <> membership.id
          )
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM staff_pin_credentials WHERE membership_id IS NULL) THEN
            RAISE EXCEPTION 'staff PIN membership backfill is ambiguous or missing';
          END IF;
        END $$
        """
    )
    op.create_foreign_key(
        "fk_staff_pin_credentials_membership_id_organization_memberships",
        "staff_pin_credentials", "organization_memberships",
        ["membership_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("pk_staff_pin_credentials", "staff_pin_credentials", type_="primary")
    op.create_primary_key("pk_staff_pin_credentials_membership", "staff_pin_credentials", ["membership_id"])
    op.create_index("ix_staff_pin_credentials_user_id", "staff_pin_credentials", ["user_id"])
    op.alter_column("staff_pin_credentials", "membership_id", existing_type=sa.Uuid(), nullable=False)

    op.create_unique_constraint(
        "uq_memberships_id_user_org_app",
        "organization_memberships",
        ["id", "user_id", "organization_id", "application_id"],
    )
    op.drop_constraint(
        "fk_owner_sessions_membership_id_organization_memberships",
        "owner_sessions", type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_owner_sessions_membership_scope",
        "owner_sessions", "organization_memberships",
        ["membership_id", "user_id", "organization_id", "application_id"],
        ["id", "user_id", "organization_id", "application_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM staff_pin_credentials
            GROUP BY user_id HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION 'cannot safely downgrade multi-membership staff PIN credentials';
          END IF;
        END $$
        """
    )
    op.drop_constraint("fk_owner_sessions_membership_scope", "owner_sessions", type_="foreignkey")
    op.create_foreign_key(
        "fk_owner_sessions_membership_id_organization_memberships",
        "owner_sessions", "organization_memberships",
        ["membership_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("uq_memberships_id_user_org_app", "organization_memberships", type_="unique")
    op.drop_index("ix_staff_pin_credentials_user_id", table_name="staff_pin_credentials")
    op.drop_constraint("pk_staff_pin_credentials_membership", "staff_pin_credentials", type_="primary")
    op.create_primary_key("pk_staff_pin_credentials", "staff_pin_credentials", ["user_id"])
    op.drop_constraint(
        "fk_staff_pin_credentials_membership_id_organization_memberships",
        "staff_pin_credentials", type_="foreignkey",
    )
    op.drop_column("staff_pin_credentials", "membership_id")
