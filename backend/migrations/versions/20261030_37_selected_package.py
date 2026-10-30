"""Record the package (Starter/Plus/Pro) an owner picked. No billing.

Revision ID: 20261030_37
Revises: 20261030_36
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261030_37"
down_revision: str | None = "20261030_36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("selected_package", sa.String(length=20), nullable=True))
    op.add_column("organizations", sa.Column("selected_package_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_organizations_selected_package", "organizations",
        "selected_package IS NULL OR selected_package IN ('starter','plus','pro')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_organizations_selected_package", "organizations", type_="check")
    op.drop_column("organizations", "selected_package_at")
    op.drop_column("organizations", "selected_package")
