"""harden JDS authentication release blockers

Revision ID: 20260802_06
Revises: 20260802_05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_06"
down_revision: str | None = "20260802_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jds_users", sa.Column("security_version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("jds_users", sa.Column("credential_state", sa.String(30), server_default="active", nullable=False))
    op.add_column("jds_users", sa.Column("recovery_started_at", sa.DateTime(timezone=True)))
    op.create_check_constraint("ck_jds_users_credential_state_valid", "jds_users", "credential_state IN ('active', 'recovery_pending')")

    op.add_column("owner_sessions", sa.Column("security_version", sa.Integer(), server_default="1", nullable=False))
    op.alter_column("owner_sessions", "security_version", server_default=None)

    op.drop_constraint("ck_owner_invitations_status_valid", "owner_invitations", type_="check")
    op.create_check_constraint("ck_owner_invitations_status_valid", "owner_invitations", "status IN ('pending_delivery', 'sent', 'accepting', 'accepted', 'revoked', 'expired', 'delivery_failed')")
    op.add_column("owner_invitations", sa.Column("secret_hash", sa.String(64)))
    op.execute("UPDATE owner_invitations SET status = 'revoked' WHERE status IN ('pending_delivery', 'sent')")
    op.execute("UPDATE owner_invitations SET secret_hash = repeat('0', 64)")
    op.alter_column("owner_invitations", "secret_hash", nullable=False)

    op.create_table(
        "auth_rate_limit_buckets",
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("lock_key", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("key_hash", name="pk_auth_rate_limit_buckets"),
    )
    op.create_index("ix_auth_rate_limit_buckets_expires_at", "auth_rate_limit_buckets", ["expires_at"])


def downgrade() -> None:
    op.drop_table("auth_rate_limit_buckets")
    op.drop_column("owner_invitations", "secret_hash")
    op.drop_constraint("ck_owner_invitations_status_valid", "owner_invitations", type_="check")
    op.execute("UPDATE owner_invitations SET status = 'revoked' WHERE status = 'accepting'")
    op.create_check_constraint("ck_owner_invitations_status_valid", "owner_invitations", "status IN ('pending_delivery', 'sent', 'accepted', 'revoked', 'expired', 'delivery_failed')")
    op.drop_column("owner_sessions", "security_version")
    op.drop_constraint("ck_jds_users_credential_state_valid", "jds_users", type_="check")
    op.drop_column("jds_users", "recovery_started_at")
    op.drop_column("jds_users", "credential_state")
    op.drop_column("jds_users", "security_version")
