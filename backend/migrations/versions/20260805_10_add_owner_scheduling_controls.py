"""add owner scheduling controls

Revision ID: 20260805_10
Revises: 20260804_09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260805_10"
down_revision: str | None = "20260804_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "business_settings",
        sa.Column("ordering_mode", sa.String(20), server_default="schedule", nullable=False),
    )
    op.create_check_constraint(
        "ck_business_settings_ordering_mode_valid",
        "business_settings",
        "ordering_mode IN ('schedule', 'force_open', 'force_closed')",
    )
    op.execute(
        "UPDATE business_settings SET ordering_mode = CASE "
        "WHEN ordering_enabled THEN 'schedule' ELSE 'force_closed' END"
    )
    op.add_column("business_closures", sa.Column("reopens_on", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_business_closures_reopens_after_start",
        "business_closures",
        "reopens_on IS NULL OR reopens_on > business_date",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_business_closures_reopens_after_start",
        "business_closures",
        type_="check",
    )
    op.drop_column("business_closures", "reopens_on")
    op.drop_constraint(
        "ck_business_settings_ordering_mode_valid",
        "business_settings",
        type_="check",
    )
    op.drop_column("business_settings", "ordering_mode")
