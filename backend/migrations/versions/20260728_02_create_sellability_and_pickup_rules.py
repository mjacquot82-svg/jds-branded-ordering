"""create sellability and pickup rules

Revision ID: 20260728_02
Revises: 20260727_01
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_02"
down_revision: str | None = "20260727_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
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
    )


def upgrade() -> None:
    op.create_table(
        "business_settings",
        sa.Column("id", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column(
            "ordering_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "minimum_lead_time_minutes",
            sa.Integer(),
            server_default="15",
            nullable=False,
        ),
        sa.Column(
            "pickup_interval_minutes",
            sa.Integer(),
            server_default="5",
            nullable=False,
        ),
        sa.Column(
            "maximum_advance_days",
            sa.Integer(),
            server_default="14",
            nullable=False,
        ),
        *timestamps(),
        sa.CheckConstraint("id = 1", name="ck_business_settings_singleton"),
        sa.CheckConstraint(
            "btrim(timezone) <> ''",
            name="ck_business_settings_timezone_nonblank",
        ),
        sa.CheckConstraint(
            "minimum_lead_time_minutes >= 0",
            name="ck_business_settings_lead_time_nonnegative",
        ),
        sa.CheckConstraint(
            "pickup_interval_minutes BETWEEN 1 AND 1440",
            name="ck_business_settings_pickup_interval_valid",
        ),
        sa.CheckConstraint(
            "maximum_advance_days BETWEEN 1 AND 365",
            name="ck_business_settings_advance_days_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_business_settings"),
    )

    op.create_table(
        "business_hours",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "business_settings_id",
            sa.SmallInteger(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column(
            "is_closed",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("opens_at", sa.Time(timezone=False), nullable=True),
        sa.Column("closes_at", sa.Time(timezone=False), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6",
            name="ck_business_hours_weekday_valid",
        ),
        sa.CheckConstraint(
            "(is_closed AND opens_at IS NULL AND closes_at IS NULL) OR "
            "(NOT is_closed AND opens_at IS NOT NULL AND closes_at IS NOT NULL "
            "AND opens_at < closes_at)",
            name="ck_business_hours_period_valid",
        ),
        sa.ForeignKeyConstraint(
            ["business_settings_id"],
            ["business_settings.id"],
            name="fk_business_hours_business_settings_id_business_settings",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_business_hours"),
        sa.UniqueConstraint(
            "business_settings_id",
            "weekday",
            name="uq_business_hours_settings_weekday",
        ),
    )
    op.create_index(
        "ix_business_hours_business_settings_id",
        "business_hours",
        ["business_settings_id"],
    )

    op.create_table(
        "business_closures",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "business_settings_id",
            sa.SmallInteger(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "reason IS NULL OR btrim(reason) <> ''",
            name="ck_business_closures_reason_nonblank",
        ),
        sa.ForeignKeyConstraint(
            ["business_settings_id"],
            ["business_settings.id"],
            name="fk_business_closures_business_settings_id_business_settings",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_business_closures"),
        sa.UniqueConstraint(
            "business_settings_id",
            "business_date",
            name="uq_business_closures_settings_date",
        ),
    )
    op.create_index(
        "ix_business_closures_business_settings_id",
        "business_closures",
        ["business_settings_id"],
    )

    op.create_table(
        "product_availability",
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "default_available",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=500), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "reason IS NULL OR btrim(reason) <> ''",
            name="ck_product_availability_reason_nonblank",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_availability_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("product_id", name="pk_product_availability"),
    )

    op.create_table(
        "product_availability_overrides",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "reason IS NULL OR btrim(reason) <> ''",
            name="ck_product_availability_overrides_reason_nonblank",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=(
                "fk_product_availability_overrides_product_id_products"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_product_availability_overrides",
        ),
        sa.UniqueConstraint(
            "product_id",
            "business_date",
            name="uq_product_availability_overrides_product_date",
        ),
    )
    op.create_index(
        "ix_product_availability_overrides_product_id",
        "product_availability_overrides",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_availability_overrides_product_id",
        table_name="product_availability_overrides",
    )
    op.drop_table("product_availability_overrides")
    op.drop_table("product_availability")
    op.drop_index(
        "ix_business_closures_business_settings_id",
        table_name="business_closures",
    )
    op.drop_table("business_closures")
    op.drop_index(
        "ix_business_hours_business_settings_id",
        table_name="business_hours",
    )
    op.drop_table("business_hours")
    op.drop_table("business_settings")
