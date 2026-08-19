"""Create the catalog domain schema.

Revision ID: 20260727_01
Revises:
Create Date: 2026-07-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260727_01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_published", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *timestamps(),
        sa.CheckConstraint("btrim(slug) <> ''", name="ck_categories_slug_nonblank"),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_categories_name_nonblank"),
        sa.CheckConstraint(
            "sort_order >= 0", name="ck_categories_sort_order_nonnegative"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
    )

    op.create_table(
        "modifier_groups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "selection_type",
            sa.String(length=20),
            server_default="single",
            nullable=False,
        ),
        sa.Column("is_required", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "minimum_selections", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "maximum_selections", sa.Integer(), server_default="1", nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "btrim(key) <> ''", name="ck_modifier_groups_key_nonblank"
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''", name="ck_modifier_groups_name_nonblank"
        ),
        sa.CheckConstraint(
            "selection_type IN ('single', 'multiple')",
            name="ck_modifier_groups_selection_type_valid",
        ),
        sa.CheckConstraint(
            "minimum_selections >= 0",
            name="ck_modifier_groups_minimum_nonnegative",
        ),
        sa.CheckConstraint(
            "maximum_selections >= 0",
            name="ck_modifier_groups_maximum_nonnegative",
        ),
        sa.CheckConstraint(
            "(is_required AND minimum_selections >= 1) "
            "OR (NOT is_required AND minimum_selections = 0)",
            name="ck_modifier_groups_required_minimum_consistent",
        ),
        sa.CheckConstraint(
            "(selection_type = 'single' AND maximum_selections = 1) "
            "OR (selection_type = 'multiple' AND "
            "(maximum_selections = 0 OR maximum_selections >= minimum_selections))",
            name="ck_modifier_groups_selection_range_valid",
        ),
        sa.CheckConstraint(
            "sort_order >= 0", name="ck_modifier_groups_sort_order_nonnegative"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_modifier_groups"),
        sa.UniqueConstraint("key", name="uq_modifier_groups_key"),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_price_cents", sa.Integer(), nullable=False),
        sa.Column("image_reference", sa.String(length=500), nullable=True),
        sa.Column(
            "is_published", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("is_featured", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *timestamps(),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("btrim(slug) <> ''", name="ck_products_slug_nonblank"),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_products_name_nonblank"),
        sa.CheckConstraint(
            "base_price_cents >= 0", name="ck_products_base_price_nonnegative"
        ),
        sa.CheckConstraint(
            "sort_order >= 0", name="ck_products_sort_order_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_products_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
    )
    op.create_index("ix_products_category_id", "products", ["category_id"])

    op.create_table(
        "product_variants",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "btrim(key) <> ''", name="ck_product_variants_key_nonblank"
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''", name="ck_product_variants_name_nonblank"
        ),
        sa.CheckConstraint(
            "price_cents >= 0", name="ck_product_variants_price_nonnegative"
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_product_variants_sort_order_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_variants_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_variants"),
        sa.UniqueConstraint(
            "product_id",
            "key",
            name="uq_product_variants_product_id_key",
        ),
    )
    op.create_index(
        "ix_product_variants_product_id", "product_variants", ["product_id"]
    )

    op.create_table(
        "modifier_options",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("modifier_group_id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "price_adjustment_cents", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "btrim(key) <> ''", name="ck_modifier_options_key_nonblank"
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''", name="ck_modifier_options_name_nonblank"
        ),
        sa.CheckConstraint(
            "price_adjustment_cents >= 0",
            name="ck_modifier_options_price_adjustment_nonnegative",
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_modifier_options_sort_order_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["modifier_group_id"],
            ["modifier_groups.id"],
            name="fk_modifier_options_modifier_group_id_modifier_groups",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_modifier_options"),
        sa.UniqueConstraint(
            "modifier_group_id",
            "key",
            name="uq_modifier_options_modifier_group_id_key",
        ),
    )
    op.create_index(
        "ix_modifier_options_modifier_group_id",
        "modifier_options",
        ["modifier_group_id"],
    )

    op.create_table(
        "product_modifier_groups",
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("modifier_group_id", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_product_modifier_groups_sort_order_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["modifier_group_id"],
            ["modifier_groups.id"],
            name=(
                "fk_product_modifier_groups_modifier_group_id_modifier_groups"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_modifier_groups_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "product_id",
            "modifier_group_id",
            name="pk_product_modifier_groups",
        ),
    )


def downgrade() -> None:
    op.drop_table("product_modifier_groups")
    op.drop_index(
        "ix_modifier_options_modifier_group_id",
        table_name="modifier_options",
    )
    op.drop_table("modifier_options")
    op.drop_index(
        "ix_product_variants_product_id",
        table_name="product_variants",
    )
    op.drop_table("product_variants")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_table("products")
    op.drop_table("modifier_groups")
    op.drop_table("categories")
