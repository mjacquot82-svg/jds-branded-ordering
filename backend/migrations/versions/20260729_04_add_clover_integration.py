"""add Clover OAuth installations and hosted checkout references

Revision ID: 20260729_04
Revises: 20260728_03
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_04"
down_revision: str | None = "20260728_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_orders_status_pending", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_status_valid",
        "orders",
        "status IN ('pending', 'payment_pending', 'paid', 'payment_failed')",
    )
    op.create_table(
        "clover_installations",
        sa.Column("merchant_id", sa.String(length=100), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("app_id", sa.String(length=100), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "merchant_id",
            "environment",
            "app_id",
            name="pk_clover_installations",
        ),
    )
    op.add_column("orders", sa.Column("clover_merchant_id", sa.String(100)))
    op.add_column(
        "orders", sa.Column("clover_checkout_session_id", sa.String(200))
    )
    op.add_column("orders", sa.Column("clover_checkout_url", sa.Text()))
    op.add_column(
        "orders", sa.Column("clover_checkout_expires_at", sa.DateTime(timezone=True))
    )
    op.create_unique_constraint(
        "uq_orders_clover_checkout_session_id",
        "orders",
        ["clover_checkout_session_id"],
    )
    op.create_check_constraint(
        "ck_orders_clover_checkout_consistent",
        "orders",
        "(clover_merchant_id IS NULL AND "
        "clover_checkout_session_id IS NULL AND "
        "clover_checkout_url IS NULL AND "
        "clover_checkout_expires_at IS NULL) OR "
        "(clover_merchant_id IS NOT NULL AND "
        "clover_checkout_session_id IS NOT NULL AND "
        "clover_checkout_url IS NOT NULL AND "
        "clover_checkout_expires_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.execute("UPDATE orders SET status = 'pending' WHERE status <> 'pending'")
    op.drop_constraint(
        "ck_orders_clover_checkout_consistent", "orders", type_="check"
    )
    op.drop_constraint(
        "uq_orders_clover_checkout_session_id", "orders", type_="unique"
    )
    op.drop_column("orders", "clover_checkout_expires_at")
    op.drop_column("orders", "clover_checkout_url")
    op.drop_column("orders", "clover_checkout_session_id")
    op.drop_column("orders", "clover_merchant_id")
    op.drop_table("clover_installations")
    op.drop_constraint("ck_orders_status_valid", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_status_pending", "orders", "status = 'pending'"
    )
