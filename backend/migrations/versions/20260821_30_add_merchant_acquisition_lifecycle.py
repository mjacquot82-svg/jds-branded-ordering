"""Add provider-neutral merchant acquisition and durable initial launch state.

Revision ID: 20260821_30
Revises: 20260820_29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_30"
down_revision: str | None = "20260820_29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organization_onboarding", sa.Column("initial_setup_completed_at", sa.DateTime(timezone=True)))
    op.add_column("organization_onboarding", sa.Column("initial_launch_source", sa.String(50)))
    op.add_column("organization_onboarding", sa.Column("initial_launch_by_user_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_onboarding_initial_launch_user", "organization_onboarding", "jds_users",
        ["initial_launch_by_user_id"], ["id"], ondelete="SET NULL",
    )
    # Preserve every merchant already treated as launched by the application.
    op.execute("UPDATE organization_onboarding SET initial_setup_completed_at=COALESCE(updated_at, now()), initial_launch_source='legacy' WHERE state='complete'")

    op.create_table(
        "merchant_acquisitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="provisioned"),
        sa.Column("external_installation_reference", sa.String(240)),
        sa.Column("verified_merchant_reference", sa.String(240)),
        sa.Column("owner_contact_hint", sa.String(320)),
        sa.Column("requested_plan_key", sa.String(50)),
        sa.Column("activation_destination", sa.String(300), nullable=False, server_default="/setup/welcome"),
        sa.Column("provider_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("provisioned_by_user_id", sa.Uuid()),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provisioned_by_user_id"], ["jds_users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", name="uq_merchant_acquisitions_organization"),
        sa.CheckConstraint("status IN ('provisioned','activation_pending','activated','revoked')", name="ck_merchant_acquisitions_status"),
    )
    op.create_index("ix_merchant_acquisitions_organization_id", "merchant_acquisitions", ["organization_id"])
    op.create_index("ix_merchant_acquisitions_source", "merchant_acquisitions", ["source"])

    op.create_table(
        "merchant_activations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("acquisition_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("intended_user_id", sa.Uuid(), nullable=False),
        sa.Column("intended_email", sa.String(320), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["acquisition_id"], ["merchant_acquisitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["membership_id"], ["organization_memberships.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["intended_user_id"], ["jds_users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('pending','used','expired','revoked')", name="ck_merchant_activations_status"),
    )
    for column in ("acquisition_id", "organization_id", "membership_id", "intended_user_id", "intended_email", "expires_at"):
        op.create_index(f"ix_merchant_activations_{column}", "merchant_activations", [column])


def downgrade() -> None:
    op.drop_table("merchant_activations")
    op.drop_table("merchant_acquisitions")
    op.drop_constraint("fk_onboarding_initial_launch_user", "organization_onboarding", type_="foreignkey")
    op.drop_column("organization_onboarding", "initial_launch_by_user_id")
    op.drop_column("organization_onboarding", "initial_launch_source")
    op.drop_column("organization_onboarding", "initial_setup_completed_at")
