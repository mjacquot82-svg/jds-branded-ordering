"""default order currency to CAD

Revision ID: 20260806_12
Revises: 20260805_11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_12"
down_revision: str | None = "20260805_11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "orders",
        "currency",
        existing_type=sa.String(length=3),
        server_default="CAD",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "orders",
        "currency",
        existing_type=sa.String(length=3),
        server_default="USD",
        existing_nullable=False,
    )
