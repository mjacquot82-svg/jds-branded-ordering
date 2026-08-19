"""create pending order domain

Revision ID: 20260728_03
Revises: 20260728_02
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_03"
down_revision: str | None = "20260728_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("public_access_token", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("guest_name", sa.String(length=200), nullable=False),
        sa.Column("guest_email", sa.String(length=320), nullable=False),
        sa.Column("guest_phone", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "requested_pickup_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("business_timezone", sa.String(length=100), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default="USD",
            nullable=False,
        ),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint(
            "status = 'pending'",
            name="ck_orders_status_pending",
        ),
        sa.CheckConstraint(
            "btrim(idempotency_key) <> ''",
            name="ck_orders_idempotency_nonblank",
        ),
        sa.CheckConstraint(
            "char_length(request_fingerprint) = 64",
            name="ck_orders_request_fingerprint_nonblank",
        ),
        sa.CheckConstraint(
            "btrim(public_access_token) <> ''",
            name="ck_orders_public_access_token_nonblank",
        ),
        sa.CheckConstraint(
            "btrim(guest_name) <> ''",
            name="ck_orders_guest_name_nonblank",
        ),
        sa.CheckConstraint(
            "btrim(guest_email) <> ''",
            name="ck_orders_guest_email_nonblank",
        ),
        sa.CheckConstraint(
            "btrim(guest_phone) <> ''",
            name="ck_orders_guest_phone_nonblank",
        ),
        sa.CheckConstraint(
            "btrim(business_timezone) <> ''",
            name="ck_orders_business_timezone_nonblank",
        ),
        sa.CheckConstraint(
            "notes IS NULL OR "
            "(btrim(notes) <> '' AND char_length(notes) <= 2000)",
            name="ck_orders_notes_valid",
        ),
        sa.CheckConstraint(
            "currency = upper(currency) AND char_length(currency) = 3",
            name="ck_orders_currency_valid",
        ),
        sa.CheckConstraint(
            "subtotal_cents >= 0",
            name="ck_orders_subtotal_nonnegative",
        ),
        sa.CheckConstraint(
            "tax_cents >= 0",
            name="ck_orders_tax_nonnegative",
        ),
        sa.CheckConstraint(
            "total_cents >= 0",
            name="ck_orders_total_nonnegative",
        ),
        sa.CheckConstraint(
            "total_cents = subtotal_cents + tax_cents",
            name="ck_orders_total_consistent",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_orders_version_positive",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_orders_expiry_after_creation",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_orders"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_orders_idempotency_key",
        ),
        sa.UniqueConstraint(
            "public_access_token",
            name="uq_orders_public_access_token",
        ),
    )

    op.create_table(
        "order_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("source_product_id", sa.BigInteger(), nullable=True),
        sa.Column("source_variant_id", sa.BigInteger(), nullable=True),
        sa.Column("product_slug", sa.String(length=100), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("variant_key", sa.String(length=100), nullable=True),
        sa.Column("variant_name", sa.String(length=200), nullable=True),
        sa.Column("base_unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_subtotal_cents", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(product_name) <> ''",
            name="ck_order_items_product_name_nonblank",
        ),
        sa.CheckConstraint(
            "btrim(product_slug) <> ''",
            name="ck_order_items_product_slug_nonblank",
        ),
        sa.CheckConstraint(
            "variant_name IS NULL OR btrim(variant_name) <> ''",
            name="ck_order_items_variant_name_nonblank",
        ),
        sa.CheckConstraint(
            "variant_key IS NULL OR btrim(variant_key) <> ''",
            name="ck_order_items_variant_key_nonblank",
        ),
        sa.CheckConstraint(
            "(source_variant_id IS NULL AND variant_name IS NULL "
            "AND variant_key IS NULL) OR "
            "(variant_name IS NOT NULL AND variant_key IS NOT NULL)",
            name="ck_order_items_variant_snapshot_consistent",
        ),
        sa.CheckConstraint(
            "quantity BETWEEN 1 AND 50",
            name="ck_order_items_quantity_valid",
        ),
        sa.CheckConstraint(
            "base_unit_price_cents >= 0",
            name="ck_order_items_base_unit_price_nonnegative",
        ),
        sa.CheckConstraint(
            "unit_price_cents >= 0",
            name="ck_order_items_unit_price_nonnegative",
        ),
        sa.CheckConstraint(
            "line_subtotal_cents = unit_price_cents * quantity",
            name="ck_order_items_line_subtotal_consistent",
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_order_items_sort_order_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_order_items_order_id_orders",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_product_id"],
            ["products.id"],
            name="fk_order_items_source_product_id_products",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_variant_id"],
            ["product_variants.id"],
            name="fk_order_items_source_variant_id_product_variants",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_order_items"),
        sa.UniqueConstraint(
            "order_id",
            "sort_order",
            name="uq_order_items_order_sort",
        ),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index(
        "ix_order_items_source_product_id",
        "order_items",
        ["source_product_id"],
    )
    op.create_index(
        "ix_order_items_source_variant_id",
        "order_items",
        ["source_variant_id"],
    )

    op.create_table(
        "order_item_modifiers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("source_modifier_group_id", sa.BigInteger(), nullable=True),
        sa.Column("source_modifier_option_id", sa.BigInteger(), nullable=True),
        sa.Column("modifier_group_key", sa.String(length=100), nullable=False),
        sa.Column("modifier_group_name", sa.String(length=200), nullable=False),
        sa.Column("modifier_option_key", sa.String(length=100), nullable=False),
        sa.Column("modifier_option_name", sa.String(length=200), nullable=False),
        sa.Column("price_adjustment_cents", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(modifier_group_key) <> ''",
            name="ck_order_item_modifiers_group_key_nonblank",
        ),
        sa.CheckConstraint(
            "btrim(modifier_group_name) <> ''",
            name="ck_order_item_modifiers_group_name_nonblank",
        ),
        sa.CheckConstraint(
            "btrim(modifier_option_key) <> ''",
            name="ck_order_item_modifiers_option_key_nonblank",
        ),
        sa.CheckConstraint(
            "btrim(modifier_option_name) <> ''",
            name="ck_order_item_modifiers_option_name_nonblank",
        ),
        sa.CheckConstraint(
            "price_adjustment_cents >= 0",
            name="ck_order_item_modifiers_price_adjustment_nonnegative",
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_order_item_modifiers_sort_order_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"],
            ["order_items.id"],
            name="fk_order_item_modifiers_order_item_id_order_items",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_modifier_group_id"],
            ["modifier_groups.id"],
            name="fk_order_item_modifiers_source_group",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_modifier_option_id"],
            ["modifier_options.id"],
            name="fk_order_item_modifiers_source_option",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_order_item_modifiers"),
        sa.UniqueConstraint(
            "order_item_id",
            "sort_order",
            name="uq_order_item_modifiers_item_sort",
        ),
    )
    op.create_index(
        "ix_order_item_modifiers_order_item_id",
        "order_item_modifiers",
        ["order_item_id"],
    )
    op.create_index(
        "ix_order_item_modifiers_source_modifier_group_id",
        "order_item_modifiers",
        ["source_modifier_group_id"],
    )
    op.create_index(
        "ix_order_item_modifiers_source_modifier_option_id",
        "order_item_modifiers",
        ["source_modifier_option_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_order_item_modifiers_source_modifier_option_id",
        table_name="order_item_modifiers",
    )
    op.drop_index(
        "ix_order_item_modifiers_source_modifier_group_id",
        table_name="order_item_modifiers",
    )
    op.drop_index(
        "ix_order_item_modifiers_order_item_id",
        table_name="order_item_modifiers",
    )
    op.drop_table("order_item_modifiers")
    op.drop_index(
        "ix_order_items_source_variant_id",
        table_name="order_items",
    )
    op.drop_index(
        "ix_order_items_source_product_id",
        table_name="order_items",
    )
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_table("orders")
