"""Add tenant ownership to the catalog and business settings spine.

Revision ID: 20260819_21
Revises: 20260818_20
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_21"
down_revision: str | None = "20260818_20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LADELS_ORGANIZATION_ID = "cd802008-80c6-5719-81ef-9b2310b16512"
LADELS_ORGANIZATION_SLUG = "the-guest-house"
LADELS_ORGANIZATION_NAME = "The Guest House"

ROOT_TABLES = ("categories", "products", "modifier_groups", "business_settings")


def _ladels_id_sql() -> str:
    return f"(SELECT id FROM organizations WHERE slug = '{LADELS_ORGANIZATION_SLUG}')"


def upgrade() -> None:
    # Preserve an existing Ladel's organization identity if already provisioned;
    # otherwise create the same deterministic UUID in every environment.
    op.execute(
        sa.text(
            "INSERT INTO organizations (id, slug, name, is_active) "
            "VALUES (CAST(:id AS uuid), :slug, :name, true) "
            "ON CONFLICT (slug) DO NOTHING"
        ).bindparams(
            id=LADELS_ORGANIZATION_ID,
            slug=LADELS_ORGANIZATION_SLUG,
            name=LADELS_ORGANIZATION_NAME,
        )
    )

    for table_name in ROOT_TABLES:
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
            f"UPDATE {table_name} SET organization_id = {_ladels_id_sql()} "
            "WHERE organization_id IS NULL"
        )

    # Replace the SmallInteger singleton key with a generated durable row key.
    op.drop_constraint("ck_business_settings_singleton", "business_settings", type_="check")
    op.alter_column(
        "business_settings",
        "id",
        existing_type=sa.SmallInteger(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        server_default=None,
    )
    op.execute("CREATE SEQUENCE business_settings_id_seq OWNED BY business_settings.id")
    op.execute(
        "SELECT setval('business_settings_id_seq', "
        "GREATEST(COALESCE((SELECT max(id) FROM business_settings), 0), 1), true)"
    )
    op.alter_column(
        "business_settings",
        "id",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        server_default=sa.text("nextval('business_settings_id_seq'::regclass)"),
    )
    for table_name in ("business_hours", "business_closures"):
        op.alter_column(
            table_name,
            "business_settings_id",
            existing_type=sa.SmallInteger(),
            type_=sa.BigInteger(),
            existing_nullable=False,
            existing_server_default="1",
        )

    op.drop_constraint("uq_categories_slug", "categories", type_="unique")
    op.drop_constraint("uq_products_slug", "products", type_="unique")
    op.drop_constraint("uq_modifier_groups_key", "modifier_groups", type_="unique")
    op.drop_index("uq_products_single_lunch_special", table_name="products")

    op.create_unique_constraint(
        "uq_categories_organization_slug", "categories", ["organization_id", "slug"]
    )
    op.create_unique_constraint(
        "uq_categories_organization_id", "categories", ["organization_id", "id"]
    )
    op.create_unique_constraint(
        "uq_products_organization_slug", "products", ["organization_id", "slug"]
    )
    op.create_unique_constraint(
        "uq_products_organization_id", "products", ["organization_id", "id"]
    )
    op.create_unique_constraint(
        "uq_modifier_groups_organization_key",
        "modifier_groups",
        ["organization_id", "key"],
    )
    op.create_unique_constraint(
        "uq_modifier_groups_organization_id",
        "modifier_groups",
        ["organization_id", "id"],
    )
    op.create_unique_constraint(
        "uq_business_settings_organization_id",
        "business_settings",
        ["organization_id"],
    )
    op.create_foreign_key(
        "fk_products_organization_category",
        "products",
        "categories",
        ["organization_id", "category_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_categories_organization_id", "categories", ["organization_id"])
    op.create_index("ix_products_organization_id", "products", ["organization_id"])
    op.create_index(
        "ix_modifier_groups_organization_id", "modifier_groups", ["organization_id"]
    )
    op.create_index(
        "ix_business_settings_organization_id", "business_settings", ["organization_id"]
    )
    op.create_index(
        "uq_products_single_lunch_special",
        "products",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("is_lunch_special IS TRUE"),
    )

    # The join table inherits ownership from both roots. A constraint trigger
    # prevents direct SQL as well as application code from crossing tenants.
    op.execute(
        """
        CREATE FUNCTION enforce_product_modifier_group_tenant() RETURNS trigger AS $$
        BEGIN
            IF (SELECT organization_id FROM products WHERE id = NEW.product_id)
               IS DISTINCT FROM
               (SELECT organization_id FROM modifier_groups WHERE id = NEW.modifier_group_id)
            THEN
                RAISE EXCEPTION 'product and modifier group must belong to the same organization'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE CONSTRAINT TRIGGER ck_product_modifier_groups_same_organization
        AFTER INSERT OR UPDATE ON product_modifier_groups
        DEFERRABLE INITIALLY IMMEDIATE
        FOR EACH ROW EXECUTE FUNCTION enforce_product_modifier_group_tenant();
        """
    )

    # Verify the backfill before contracting ownership to NOT NULL.
    op.execute(
        """
        DO $$
        DECLARE table_name text; invalid_count bigint;
        BEGIN
            FOREACH table_name IN ARRAY ARRAY[
                'categories', 'products', 'modifier_groups', 'business_settings'
            ] LOOP
                EXECUTE format(
                    'SELECT count(*) FROM %I root LEFT JOIN organizations org '
                    'ON org.id = root.organization_id '
                    'WHERE root.organization_id IS NULL OR org.id IS NULL',
                    table_name
                ) INTO invalid_count;
                IF invalid_count <> 0 THEN
                    RAISE EXCEPTION 'tenant ownership verification failed for %', table_name;
                END IF;
            END LOOP;
            IF EXISTS (
                SELECT 1 FROM product_modifier_groups assignment
                JOIN products product ON product.id = assignment.product_id
                JOIN modifier_groups modifier_group
                  ON modifier_group.id = assignment.modifier_group_id
                WHERE product.organization_id <> modifier_group.organization_id
            ) THEN
                RAISE EXCEPTION 'cross-tenant product modifier assignment found';
            END IF;
        END $$;
        """
    )
    for table_name in ROOT_TABLES:
        op.alter_column(
            table_name,
            "organization_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )


def downgrade() -> None:
    # Restoring global uniqueness is safe only while this is still the original
    # single-tenant dataset. Refuse a destructive downgrade once tenant data exists.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM (
                    SELECT organization_id FROM categories
                    UNION SELECT organization_id FROM products
                    UNION SELECT organization_id FROM modifier_groups
                    UNION SELECT organization_id FROM business_settings
                ) owned
                WHERE organization_id <> {_ladels_id_sql()}
            ) OR (SELECT count(*) FROM business_settings) > 1 THEN
                RAISE EXCEPTION 'cannot safely downgrade tenant catalog data';
            END IF;
        END $$;
        """
    )

    op.execute(
        "DROP TRIGGER ck_product_modifier_groups_same_organization "
        "ON product_modifier_groups"
    )
    op.execute("DROP FUNCTION enforce_product_modifier_group_tenant()")
    op.drop_constraint("fk_products_organization_category", "products", type_="foreignkey")
    op.drop_index("uq_products_single_lunch_special", table_name="products")
    for table_name in ROOT_TABLES:
        op.drop_index(f"ix_{table_name}_organization_id", table_name=table_name)

    op.drop_constraint(
        "uq_business_settings_organization_id", "business_settings", type_="unique"
    )
    op.drop_constraint(
        "uq_modifier_groups_organization_id", "modifier_groups", type_="unique"
    )
    op.drop_constraint(
        "uq_modifier_groups_organization_key", "modifier_groups", type_="unique"
    )
    op.drop_constraint("uq_products_organization_id", "products", type_="unique")
    op.drop_constraint("uq_products_organization_slug", "products", type_="unique")
    op.drop_constraint("uq_categories_organization_id", "categories", type_="unique")
    op.drop_constraint("uq_categories_organization_slug", "categories", type_="unique")

    op.create_unique_constraint("uq_categories_slug", "categories", ["slug"])
    op.create_unique_constraint("uq_products_slug", "products", ["slug"])
    op.create_unique_constraint("uq_modifier_groups_key", "modifier_groups", ["key"])
    op.create_index(
        "uq_products_single_lunch_special",
        "products",
        ["is_lunch_special"],
        unique=True,
        postgresql_where=sa.text("is_lunch_special IS TRUE"),
    )

    for table_name in ROOT_TABLES:
        op.drop_constraint(
            f"fk_{table_name}_organization_id_organizations",
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, "organization_id")

    for table_name in ("business_hours", "business_closures"):
        op.alter_column(
            table_name,
            "business_settings_id",
            existing_type=sa.BigInteger(),
            type_=sa.SmallInteger(),
            existing_nullable=False,
            existing_server_default="1",
        )
    op.alter_column(
        "business_settings",
        "id",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        server_default=None,
    )
    op.execute("DROP SEQUENCE business_settings_id_seq")
    op.alter_column(
        "business_settings",
        "id",
        existing_type=sa.BigInteger(),
        type_=sa.SmallInteger(),
        existing_nullable=False,
        server_default="1",
    )
    op.create_check_constraint(
        "ck_business_settings_singleton", "business_settings", "id = 1"
    )
