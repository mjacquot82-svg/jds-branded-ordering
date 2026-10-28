"""Pay at pickup: per-shop order settings, no-show blocks.

Revision ID: 20261020_34
Revises: 20260910_33
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_34"
down_revision: str | None = "20260910_33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_order_settings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("pay_at_pickup_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("pay_at_pickup_min_completed_orders", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pay_at_pickup_max_total_cents", sa.Integer(), nullable=False, server_default="2500"),
        sa.Column("new_order_alert_email", sa.String(length=320), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_org_order_settings_organization", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("organization_id", name="pk_organization_order_settings"),
        sa.CheckConstraint("pay_at_pickup_min_completed_orders BETWEEN 0 AND 100", name="ck_org_order_settings_min_completed"),
        sa.CheckConstraint("pay_at_pickup_max_total_cents BETWEEN 100 AND 100000", name="ck_org_order_settings_max_total"),
    )
    op.create_table(
        "pay_at_pickup_blocks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("customer_user_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(length=40), nullable=False, server_default="no_show"),
        sa.Column("blocked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_pay_at_pickup_blocks_organization", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_user_id"], ["jds_users.id"], name="fk_pay_at_pickup_blocks_customer", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_pay_at_pickup_blocks"),
        sa.UniqueConstraint("organization_id", "customer_user_id", name="uq_pay_at_pickup_blocks_org_customer"),
    )
    op.create_index("ix_pay_at_pickup_blocks_organization_id", "pay_at_pickup_blocks", ["organization_id"])
    op.create_index("ix_pay_at_pickup_blocks_customer_user_id", "pay_at_pickup_blocks", ["customer_user_id"])


def downgrade() -> None:
    op.drop_index("ix_pay_at_pickup_blocks_customer_user_id", table_name="pay_at_pickup_blocks")
    op.drop_index("ix_pay_at_pickup_blocks_organization_id", table_name="pay_at_pickup_blocks")
    op.drop_table("pay_at_pickup_blocks")
    op.drop_table("organization_order_settings")
