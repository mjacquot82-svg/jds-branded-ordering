"""add order fulfillment operations

Revision ID: 20260805_11
Revises: 20260805_10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260805_11"
down_revision: str | None = "20260805_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "fulfillment_status",
            sa.String(length=30),
            server_default="new",
            nullable=False,
        ),
    )
    op.add_column(
        "orders", sa.Column("fulfillment_updated_at", sa.DateTime(timezone=True))
    )
    op.add_column("orders", sa.Column("preparing_at", sa.DateTime(timezone=True)))
    op.add_column("orders", sa.Column("ready_at", sa.DateTime(timezone=True)))
    op.add_column("orders", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.add_column("orders", sa.Column("cancelled_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_orders_fulfillment_status_valid",
        "orders",
        "fulfillment_status IN "
        "('new', 'preparing', 'ready', 'completed', 'cancelled')",
    )
    op.create_index(
        "ix_orders_fulfillment_status", "orders", ["fulfillment_status"]
    )
    op.create_index(
        "ix_orders_active_queue",
        "orders",
        ["status", "fulfillment_status", "requested_pickup_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_orders_active_queue", table_name="orders")
    op.drop_index("ix_orders_fulfillment_status", table_name="orders")
    op.drop_constraint(
        "ck_orders_fulfillment_status_valid", "orders", type_="check"
    )
    op.drop_column("orders", "cancelled_at")
    op.drop_column("orders", "completed_at")
    op.drop_column("orders", "ready_at")
    op.drop_column("orders", "preparing_at")
    op.drop_column("orders", "fulfillment_updated_at")
    op.drop_column("orders", "fulfillment_status")
