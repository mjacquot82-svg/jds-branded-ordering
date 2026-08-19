"""Add tenant ownership to orders and fulfillment queries.

Revision ID: 20260820_23
Revises: 20260819_22
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_23"
down_revision: str | None = "20260819_22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LADELS_ORGANIZATION_SLUG = "the-guest-house"


def _ladels_id_sql() -> str:
    return f"(SELECT id FROM organizations WHERE slug = '{LADELS_ORGANIZATION_SLUG}')"


def upgrade() -> None:
    op.add_column("orders", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_orders_organization_id_organizations",
        "orders",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        f"UPDATE orders SET organization_id = {_ladels_id_sql()} "
        "WHERE organization_id IS NULL"
    )
    op.execute(
        f"""
        DO $$
        DECLARE invalid_count bigint;
        BEGIN
            IF {_ladels_id_sql()} IS NULL THEN
                RAISE EXCEPTION 'Ladel''s organization is missing';
            END IF;
            SELECT count(*) INTO invalid_count
            FROM orders orders_row
            LEFT JOIN organizations organization
              ON organization.id = orders_row.organization_id
            WHERE orders_row.organization_id IS NULL OR organization.id IS NULL;
            IF invalid_count <> 0 THEN
                RAISE EXCEPTION 'order tenant ownership verification failed';
            END IF;
            SELECT count(*) INTO invalid_count
            FROM orders
            WHERE organization_id <> {_ladels_id_sql()};
            IF invalid_count <> 0 THEN
                RAISE EXCEPTION 'non-Ladel tenant orders existed before order migration';
            END IF;
        END $$;
        """
    )

    op.drop_index("ix_orders_active_queue", table_name="orders")
    op.drop_index("ix_orders_fulfillment_status", table_name="orders")
    op.drop_constraint("uq_orders_idempotency_key", "orders", type_="unique")
    op.drop_constraint("uq_orders_public_access_token", "orders", type_="unique")

    op.create_unique_constraint(
        "uq_orders_organization_id_id",
        "orders",
        ["organization_id", "id"],
    )
    op.create_unique_constraint(
        "uq_orders_organization_idempotency_key",
        "orders",
        ["organization_id", "idempotency_key"],
    )
    op.create_unique_constraint(
        "uq_orders_organization_public_access_token",
        "orders",
        ["organization_id", "public_access_token"],
    )
    op.create_index(
        "ix_orders_organization_id", "orders", ["organization_id"]
    )
    op.create_index(
        "ix_orders_organization_active_queue",
        "orders",
        [
            "organization_id",
            "status",
            "fulfillment_status",
            "requested_pickup_at",
            "created_at",
        ],
    )
    op.create_index(
        "ix_orders_organization_customer_created",
        "orders",
        ["organization_id", "customer_user_id", "created_at"],
    )
    op.create_index(
        "ix_orders_organization_fulfillment_pickup",
        "orders",
        ["organization_id", "fulfillment_status", "requested_pickup_at"],
    )
    op.alter_column(
        "orders",
        "organization_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        DECLARE tenant_count bigint;
        BEGIN
            SELECT count(*) INTO tenant_count
            FROM orders
            WHERE organization_id <> {_ladels_id_sql()};
            IF tenant_count <> 0 THEN
                RAISE EXCEPTION 'cannot safely downgrade tenant order data';
            END IF;
        END $$;
        """
    )

    op.drop_index(
        "ix_orders_organization_fulfillment_pickup", table_name="orders"
    )
    op.drop_index("ix_orders_organization_customer_created", table_name="orders")
    op.drop_index("ix_orders_organization_active_queue", table_name="orders")
    op.drop_index("ix_orders_organization_id", table_name="orders")
    op.drop_constraint(
        "uq_orders_organization_public_access_token", "orders", type_="unique"
    )
    op.drop_constraint(
        "uq_orders_organization_idempotency_key", "orders", type_="unique"
    )
    op.drop_constraint("uq_orders_organization_id_id", "orders", type_="unique")

    op.create_unique_constraint(
        "uq_orders_idempotency_key", "orders", ["idempotency_key"]
    )
    op.create_unique_constraint(
        "uq_orders_public_access_token", "orders", ["public_access_token"]
    )
    op.create_index(
        "ix_orders_fulfillment_status", "orders", ["fulfillment_status"]
    )
    op.create_index(
        "ix_orders_active_queue",
        "orders",
        ["status", "fulfillment_status", "requested_pickup_at", "created_at"],
    )
    op.drop_constraint(
        "fk_orders_organization_id_organizations", "orders", type_="foreignkey"
    )
    op.drop_column("orders", "organization_id")
