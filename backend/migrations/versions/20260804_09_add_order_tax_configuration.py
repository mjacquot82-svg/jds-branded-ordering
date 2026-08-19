"""add authoritative order tax configuration

Revision ID: 20260804_09
Revises: 20260804_08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_09"
down_revision: str | None = "20260804_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("business_settings", sa.Column("tax_name", sa.String(50), server_default="HST", nullable=False))
    op.add_column("business_settings", sa.Column("tax_rate_millionths", sa.Integer(), server_default="1300000", nullable=False))
    op.create_check_constraint("ck_business_settings_tax_name_nonblank", "business_settings", "btrim(tax_name) <> ''")
    op.create_check_constraint("ck_business_settings_tax_rate_millionths_valid", "business_settings", "tax_rate_millionths BETWEEN 0 AND 10000000")
    op.execute(
        "INSERT INTO business_settings "
        "(id, timezone, ordering_enabled, minimum_lead_time_minutes, "
        "pickup_interval_minutes, maximum_advance_days, tax_name, "
        "tax_rate_millionths) VALUES "
        "(1, 'America/Toronto', true, 15, 5, 14, 'HST', 1300000) "
        "ON CONFLICT (id) DO NOTHING"
    )
    op.add_column("orders", sa.Column("tax_name", sa.String(50), server_default="HST", nullable=False))
    op.add_column("orders", sa.Column("tax_rate_millionths", sa.Integer(), server_default="1300000", nullable=False))
    op.create_check_constraint("ck_orders_tax_name_nonblank", "orders", "btrim(tax_name) <> ''")
    op.create_check_constraint("ck_orders_tax_rate_millionths_valid", "orders", "tax_rate_millionths BETWEEN 0 AND 10000000")


def downgrade() -> None:
    op.drop_constraint("ck_orders_tax_rate_millionths_valid", "orders", type_="check")
    op.drop_constraint("ck_orders_tax_name_nonblank", "orders", type_="check")
    op.drop_column("orders", "tax_rate_millionths")
    op.drop_column("orders", "tax_name")
    op.drop_constraint("ck_business_settings_tax_rate_millionths_valid", "business_settings", type_="check")
    op.drop_constraint("ck_business_settings_tax_name_nonblank", "business_settings", type_="check")
    op.drop_column("business_settings", "tax_rate_millionths")
    op.drop_column("business_settings", "tax_name")
