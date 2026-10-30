"""Platform subscription billing, usage counters, billing_exempt (existing shops exempt).

Revision ID: 20261030_38
Revises: 20261030_37
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261030_38"
down_revision: str | None = "20261030_37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("billing_exempt", sa.Boolean(), server_default="false", nullable=False))
    # Every shop that exists today is a beta shop: keep it free even after billing is switched on.
    op.execute("UPDATE organizations SET billing_exempt = true")
    op.create_table(
        "shop_billing_accounts",
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", sa.String(20), server_default="none", nullable=False),
        sa.Column("package_key", sa.String(20)),
        sa.Column("pending_package_key", sa.String(20)),
        sa.Column("extra_locations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("monthly_amount_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(3), server_default="CAD", nullable=False),
        sa.Column("square_customer_id", sa.String(200)),
        sa.Column("square_card_id", sa.String(200)),
        sa.Column("square_subscription_id", sa.String(200), unique=True),
        sa.Column("card_brand", sa.String(40)),
        sa.Column("card_last4", sa.String(4)),
        sa.Column("card_exp_month", sa.Integer()),
        sa.Column("card_exp_year", sa.Integer()),
        sa.Column("next_bill_on", sa.Date()),
        sa.Column("past_due_since", sa.DateTime(timezone=True)),
        sa.Column("grace_ends_at", sa.DateTime(timezone=True)),
        sa.Column("paused_at", sa.DateTime(timezone=True)),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True)),
        sa.Column("reminder_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('none','active','past_due','paused','cancelled')", name="ck_shop_billing_accounts_status"),
        sa.CheckConstraint("extra_locations >= 0", name="ck_shop_billing_accounts_extra_locations"),
        sa.CheckConstraint("package_key IS NULL OR package_key IN ('starter','plus','pro')", name="ck_shop_billing_accounts_package"),
        sa.CheckConstraint("pending_package_key IS NULL OR pending_package_key IN ('starter','plus','pro')", name="ck_shop_billing_accounts_pending_package"),
    )
    op.create_index("ix_shop_billing_accounts_square_customer_id", "shop_billing_accounts", ["square_customer_id"])
    op.create_table(
        "billing_payments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_event_id", sa.String(200), nullable=False, unique=True),
        sa.Column("provider_invoice_id", sa.String(200)),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("amount_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(3), server_default="CAD", nullable=False),
        sa.Column("package_key", sa.String(20)),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("outcome IN ('paid','failed')", name="ck_billing_payments_outcome"),
    )
    op.create_index("ix_billing_payments_organization_id", "billing_payments", ["organization_id"])
    op.create_index("ix_billing_payments_period", "billing_payments", ["period"])
    op.create_table(
        "shop_usage_counters",
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("period", sa.String(7), primary_key=True),
        sa.Column("metric", sa.String(40), primary_key=True),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("shop_usage_counters")
    op.drop_index("ix_billing_payments_period", table_name="billing_payments")
    op.drop_index("ix_billing_payments_organization_id", table_name="billing_payments")
    op.drop_table("billing_payments")
    op.drop_index("ix_shop_billing_accounts_square_customer_id", table_name="shop_billing_accounts")
    op.drop_table("shop_billing_accounts")
    op.drop_column("organizations", "billing_exempt")
