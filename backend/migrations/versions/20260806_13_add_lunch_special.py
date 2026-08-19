"""add lunch special product designation

Revision ID: 20260806_13
Revises: 20260806_12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_13"
down_revision: str | None = "20260806_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "is_lunch_special",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "uq_products_single_lunch_special",
        "products",
        ["is_lunch_special"],
        unique=True,
        postgresql_where=sa.text("is_lunch_special IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_products_single_lunch_special", table_name="products")
    op.drop_column("products", "is_lunch_special")
