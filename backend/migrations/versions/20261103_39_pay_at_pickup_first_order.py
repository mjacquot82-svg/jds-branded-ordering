"""Pay at pickup works on a customer's first order: default min completed orders 1 -> 0.

Revision ID: 20261103_39
Revises: 20261030_38

The table has no "changed by owner" marker, so a shop that never touched the setting
cannot be told apart from one that deliberately saved 1. Every shop today is a beta
shop, so all rows still at the old default of 1 move to 0. Owners can raise it again in
Order settings. Rows with any other value (0, 2+) are left alone.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261103_39"
down_revision: str | None = "20261030_38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("organization_order_settings", "pay_at_pickup_min_completed_orders", server_default=sa.text("0"))
    op.execute("UPDATE organization_order_settings SET pay_at_pickup_min_completed_orders = 0 WHERE pay_at_pickup_min_completed_orders = 1")


def downgrade() -> None:
    op.alter_column("organization_order_settings", "pay_at_pickup_min_completed_orders", server_default=sa.text("1"))
