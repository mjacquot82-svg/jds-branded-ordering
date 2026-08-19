"""Add tenant ownership to availability and scheduling records.

Revision ID: 20260819_22
Revises: 20260819_21
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_22"
down_revision: str | None = "20260819_21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LADELS_ORGANIZATION_SLUG = "the-guest-house"
OWNED_TABLES = (
    "business_hours",
    "business_closures",
    "product_availability",
    "product_availability_overrides",
)


def _ladels_id_sql() -> str:
    return f"(SELECT id FROM organizations WHERE slug = '{LADELS_ORGANIZATION_SLUG}')"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_business_settings_organization_id_id",
        "business_settings",
        ["organization_id", "id"],
    )

    for table_name in OWNED_TABLES:
        op.add_column(table_name, sa.Column("organization_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{table_name}_organization_id_organizations",
            table_name,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.execute(
        "UPDATE business_hours child SET organization_id = parent.organization_id "
        "FROM business_settings parent "
        "WHERE child.business_settings_id = parent.id AND child.organization_id IS NULL"
    )
    op.execute(
        "UPDATE business_closures child SET organization_id = parent.organization_id "
        "FROM business_settings parent "
        "WHERE child.business_settings_id = parent.id AND child.organization_id IS NULL"
    )
    for table_name in ("product_availability", "product_availability_overrides"):
        op.execute(
            f"UPDATE {table_name} child SET organization_id = parent.organization_id "
            "FROM products parent "
            "WHERE child.product_id = parent.id AND child.organization_id IS NULL"
        )

    op.execute(
        f"""
        DO $$
        DECLARE table_name text; invalid_count bigint;
        BEGIN
            IF {_ladels_id_sql()} IS NULL THEN
                RAISE EXCEPTION 'Ladel''s organization is missing';
            END IF;
            FOREACH table_name IN ARRAY ARRAY[
                'business_hours', 'business_closures',
                'product_availability', 'product_availability_overrides'
            ] LOOP
                EXECUTE format(
                    'SELECT count(*) FROM %I child LEFT JOIN organizations org '
                    'ON org.id = child.organization_id '
                    'WHERE child.organization_id IS NULL OR org.id IS NULL',
                    table_name
                ) INTO invalid_count;
                IF invalid_count <> 0 THEN
                    RAISE EXCEPTION 'tenant ownership verification failed for %', table_name;
                END IF;
                EXECUTE format(
                    'SELECT count(*) FROM %I WHERE organization_id <> $1', table_name
                ) INTO invalid_count USING {_ladels_id_sql()};
                IF invalid_count <> 0 THEN
                    RAISE EXCEPTION 'non-Ladel tenant data existed before availability migration in %', table_name;
                END IF;
            END LOOP;
        END $$;
        """
    )

    op.drop_constraint(
        "fk_business_hours_business_settings_id_business_settings",
        "business_hours",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_business_closures_business_settings_id_business_settings",
        "business_closures",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_product_availability_product_id_products",
        "product_availability",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_product_availability_overrides_product_id_products",
        "product_availability_overrides",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_business_hours_settings_weekday", "business_hours", type_="unique"
    )
    op.drop_constraint(
        "uq_business_closures_settings_date", "business_closures", type_="unique"
    )
    op.drop_constraint(
        "uq_product_availability_overrides_product_date",
        "product_availability_overrides",
        type_="unique",
    )
    for table_name in ("business_hours", "business_closures"):
        op.alter_column(
            table_name,
            "business_settings_id",
            existing_type=sa.BigInteger(),
            existing_nullable=False,
            server_default=None,
        )

    op.create_unique_constraint(
        "uq_business_hours_organization_weekday",
        "business_hours",
        ["organization_id", "weekday"],
    )
    op.create_unique_constraint(
        "uq_business_closures_organization_date",
        "business_closures",
        ["organization_id", "business_date"],
    )
    op.create_unique_constraint(
        "uq_product_availability_overrides_organization_product_date",
        "product_availability_overrides",
        ["organization_id", "product_id", "business_date"],
    )
    op.create_foreign_key(
        "fk_business_hours_organization_settings",
        "business_hours",
        "business_settings",
        ["organization_id", "business_settings_id"],
        ["organization_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_business_closures_organization_settings",
        "business_closures",
        "business_settings",
        ["organization_id", "business_settings_id"],
        ["organization_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_product_availability_organization_product",
        "product_availability",
        "products",
        ["organization_id", "product_id"],
        ["organization_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_product_availability_overrides_organization_product",
        "product_availability_overrides",
        "products",
        ["organization_id", "product_id"],
        ["organization_id", "id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_business_hours_organization_id", "business_hours", ["organization_id"]
    )
    op.create_index(
        "ix_business_closures_organization_id",
        "business_closures",
        ["organization_id"],
    )
    op.create_index(
        "ix_product_availability_organization_id",
        "product_availability",
        ["organization_id"],
    )
    op.create_index(
        "ix_product_availability_overrides_organization_id",
        "product_availability_overrides",
        ["organization_id"],
    )
    op.create_index(
        "ix_product_availability_overrides_organization_date",
        "product_availability_overrides",
        ["organization_id", "business_date"],
    )

    for table_name in OWNED_TABLES:
        op.alter_column(
            table_name, "organization_id", existing_type=sa.Uuid(), nullable=False
        )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        DECLARE table_name text; tenant_count bigint;
        BEGIN
            FOREACH table_name IN ARRAY ARRAY[
                'business_hours', 'business_closures',
                'product_availability', 'product_availability_overrides'
            ] LOOP
                EXECUTE format(
                    'SELECT count(*) FROM %I WHERE organization_id <> $1', table_name
                ) INTO tenant_count USING {_ladels_id_sql()};
                IF tenant_count <> 0 THEN
                    RAISE EXCEPTION 'cannot safely downgrade tenant availability data';
                END IF;
            END LOOP;
        END $$;
        """
    )

    op.drop_index(
        "ix_product_availability_overrides_organization_date",
        table_name="product_availability_overrides",
    )
    for table_name in reversed(OWNED_TABLES):
        op.drop_index(f"ix_{table_name}_organization_id", table_name=table_name)

    op.drop_constraint(
        "fk_product_availability_overrides_organization_product",
        "product_availability_overrides",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_product_availability_organization_product",
        "product_availability",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_business_closures_organization_settings",
        "business_closures",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_business_hours_organization_settings",
        "business_hours",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_product_availability_overrides_organization_product_date",
        "product_availability_overrides",
        type_="unique",
    )
    op.drop_constraint(
        "uq_business_closures_organization_date", "business_closures", type_="unique"
    )
    op.drop_constraint(
        "uq_business_hours_organization_weekday", "business_hours", type_="unique"
    )

    op.create_foreign_key(
        "fk_business_hours_business_settings_id_business_settings",
        "business_hours",
        "business_settings",
        ["business_settings_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_business_closures_business_settings_id_business_settings",
        "business_closures",
        "business_settings",
        ["business_settings_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_product_availability_product_id_products",
        "product_availability",
        "products",
        ["product_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_product_availability_overrides_product_id_products",
        "product_availability_overrides",
        "products",
        ["product_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_business_hours_settings_weekday",
        "business_hours",
        ["business_settings_id", "weekday"],
    )
    op.create_unique_constraint(
        "uq_business_closures_settings_date",
        "business_closures",
        ["business_settings_id", "business_date"],
    )
    op.create_unique_constraint(
        "uq_product_availability_overrides_product_date",
        "product_availability_overrides",
        ["product_id", "business_date"],
    )
    for table_name in ("business_hours", "business_closures"):
        op.alter_column(
            table_name,
            "business_settings_id",
            existing_type=sa.BigInteger(),
            existing_nullable=False,
            server_default="1",
        )

    for table_name in OWNED_TABLES:
        op.drop_constraint(
            f"fk_{table_name}_organization_id_organizations",
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, "organization_id")
    op.drop_constraint(
        "uq_business_settings_organization_id_id", "business_settings", type_="unique"
    )
