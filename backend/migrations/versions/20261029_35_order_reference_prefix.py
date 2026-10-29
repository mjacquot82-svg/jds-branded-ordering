"""Per-shop order number prefix.

Revision ID: 20261029_35
Revises: 20261020_34
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261029_35"
down_revision: str | None = "20261020_34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("reference_prefix", sa.String(length=8), nullable=True))
    # Existing orders keep the numbers staff and customers already saw.
    op.execute("UPDATE orders SET reference_prefix = 'GH' WHERE reference_prefix IS NULL")


def downgrade() -> None:
    op.drop_column("orders", "reference_prefix")
