"""Square payment provider: seller connections and OAuth state.

Revision ID: 20261030_36
Revises: 20261029_35
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261030_36"
down_revision: str | None = "20261029_35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "square_installations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("merchant_id", sa.String(length=100), nullable=False),
        sa.Column("application_id", sa.String(length=100), nullable=False),
        sa.Column("location_id", sa.String(length=100), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("connection_state", sa.String(length=30), server_default="connected", nullable=False),
        sa.Column("reconnect_reason", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "environment", name="uq_square_installations_org_env"),
        sa.UniqueConstraint("environment", "merchant_id", name="uq_square_installations_env_merchant"),
    )
    op.create_index("ix_square_installations_organization_id", "square_installations", ["organization_id"])
    op.create_index("ix_square_installations_org_state", "square_installations",
                    ["organization_id", "connection_state"])
    op.create_table(
        "square_oauth_states",
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("application_id", sa.String(length=100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("nonce_hash"),
    )
    op.create_index("ix_square_oauth_states_org_expires", "square_oauth_states",
                    ["organization_id", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_square_oauth_states_org_expires", table_name="square_oauth_states")
    op.drop_table("square_oauth_states")
    op.drop_index("ix_square_installations_org_state", table_name="square_installations")
    op.drop_index("ix_square_installations_organization_id", table_name="square_installations")
    op.drop_table("square_installations")
