"""Add tenant ownership to Clover installations and payment evidence.

Revision ID: 20260822_25
Revises: 20260821_24
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_25"
down_revision: str | None = "20260821_24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LADELS_ID = "(SELECT id FROM organizations WHERE slug = 'the-guest-house')"


def upgrade() -> None:
    op.add_column("clover_installations", sa.Column("id", sa.Uuid(), nullable=True))
    op.add_column("clover_installations", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.add_column("clover_installations", sa.Column("page_config_uuid", sa.String(200), nullable=True))
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM clover_installations
            GROUP BY environment, merchant_id HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION 'ambiguous Clover merchant installation mapping';
          END IF;
        END $$
    """)
    op.execute(f"UPDATE clover_installations SET organization_id = {LADELS_ID}, id = CAST(md5(environment || ':' || merchant_id || ':' || app_id) AS uuid)")
    op.execute(f"""
        DO $$ BEGIN
          IF {LADELS_ID} IS NULL THEN RAISE EXCEPTION 'Ladel''s organization is missing'; END IF;
          IF EXISTS (SELECT 1 FROM clover_installations WHERE organization_id IS NULL OR id IS NULL) THEN
            RAISE EXCEPTION 'Clover installation tenant backfill failed';
          END IF;
        END $$
    """)
    op.create_foreign_key("fk_clover_installations_organization_id_organizations", "clover_installations", "organizations", ["organization_id"], ["id"], ondelete="RESTRICT")
    op.create_unique_constraint("uq_clover_installations_id", "clover_installations", ["id"])
    op.create_unique_constraint("uq_clover_installations_organization_id_id", "clover_installations", ["organization_id", "id"])
    op.create_unique_constraint("uq_clover_installations_tenant_identity", "clover_installations", ["organization_id", "id", "environment", "merchant_id"])
    op.create_unique_constraint("uq_clover_installations_organization_environment", "clover_installations", ["organization_id", "environment"])
    op.create_unique_constraint("uq_clover_installations_environment_merchant", "clover_installations", ["environment", "merchant_id"])
    op.create_index("ix_clover_installations_organization_id", "clover_installations", ["organization_id"])
    op.create_index("ix_clover_installations_organization_state", "clover_installations", ["organization_id", "connection_state"])
    op.alter_column("clover_installations", "id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("clover_installations", "organization_id", existing_type=sa.Uuid(), nullable=False)

    op.add_column("orders", sa.Column("clover_installation_id", sa.Uuid(), nullable=True))
    op.add_column("orders", sa.Column("clover_environment", sa.String(20), nullable=True))
    op.execute("""
        UPDATE orders order_row SET clover_installation_id = installation.id, clover_environment = installation.environment
        FROM clover_installations installation
        WHERE order_row.clover_merchant_id = installation.merchant_id
          AND order_row.organization_id = installation.organization_id
    """)
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM orders WHERE clover_merchant_id IS NOT NULL AND clover_installation_id IS NULL) THEN
            RAISE EXCEPTION 'Clover order installation backfill failed';
          END IF;
        END $$
    """)
    op.drop_constraint("ck_orders_clover_checkout_consistent", "orders", type_="check")
    op.create_check_constraint("ck_orders_clover_checkout_consistent", "orders", "(clover_installation_id IS NULL AND clover_environment IS NULL AND clover_merchant_id IS NULL AND clover_checkout_session_id IS NULL AND clover_checkout_url IS NULL AND clover_checkout_expires_at IS NULL) OR (clover_installation_id IS NOT NULL AND clover_environment IS NOT NULL AND clover_merchant_id IS NOT NULL AND clover_checkout_session_id IS NOT NULL AND clover_checkout_url IS NOT NULL AND clover_checkout_expires_at IS NOT NULL)")
    op.create_foreign_key("fk_orders_tenant_clover_installation", "orders", "clover_installations", ["organization_id", "clover_installation_id", "clover_environment", "clover_merchant_id"], ["organization_id", "id", "environment", "merchant_id"], ondelete="RESTRICT")
    op.drop_constraint("uq_orders_clover_checkout_session_id", "orders", type_="unique")
    op.create_unique_constraint("uq_orders_organization_clover_checkout_session", "orders", ["organization_id", "clover_checkout_session_id"])
    op.create_index("ix_orders_clover_installation_id", "orders", ["clover_installation_id"])
    op.create_index("ix_orders_organization_clover_checkout", "orders", ["organization_id", "clover_checkout_session_id"])

    op.add_column("clover_payment_events", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.add_column("clover_payment_events", sa.Column("installation_id", sa.Uuid(), nullable=True))
    op.execute("""
        UPDATE clover_payment_events event SET organization_id = installation.organization_id, installation_id = installation.id
        FROM clover_installations installation
        WHERE event.environment = installation.environment AND event.merchant_id = installation.merchant_id
    """)
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM clover_payment_events WHERE organization_id IS NULL OR installation_id IS NULL) THEN
            RAISE EXCEPTION 'Clover payment-event tenant backfill failed';
          END IF;
        END $$
    """)
    op.drop_constraint("uq_clover_payment_events_environment_merchant_payment", "clover_payment_events", type_="unique")
    op.create_unique_constraint("uq_clover_payment_events_installation_payment", "clover_payment_events", ["installation_id", "payment_id"])
    op.create_foreign_key("fk_clover_payment_events_tenant_installation", "clover_payment_events", "clover_installations", ["organization_id", "installation_id", "environment", "merchant_id"], ["organization_id", "id", "environment", "merchant_id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_clover_payment_events_tenant_order", "clover_payment_events", "orders", ["organization_id", "order_id"], ["organization_id", "id"], ondelete="RESTRICT")
    op.create_index("ix_clover_payment_events_organization_id", "clover_payment_events", ["organization_id"])
    op.create_index("ix_clover_payment_events_installation_id", "clover_payment_events", ["installation_id"])
    op.create_index("ix_clover_payment_events_organization_created", "clover_payment_events", ["organization_id", "created_at"])
    op.create_index("ix_clover_payment_events_organization_checkout", "clover_payment_events", ["organization_id", "checkout_session_id"])
    op.alter_column("clover_payment_events", "organization_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("clover_payment_events", "installation_id", existing_type=sa.Uuid(), nullable=False)

    op.create_table(
        "clover_oauth_states",
        sa.Column("nonce_hash", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("app_id", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["membership_id"], ["organization_memberships.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_clover_oauth_states_organization_expires", "clover_oauth_states", ["organization_id", "expires_at"])


def downgrade() -> None:
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM clover_installations WHERE organization_id <> {LADELS_ID}) THEN
            RAISE EXCEPTION 'cannot safely downgrade multi-tenant Clover installations';
          END IF;
        END $$
    """)
    op.drop_table("clover_oauth_states")
    op.drop_index("ix_clover_payment_events_organization_checkout", table_name="clover_payment_events")
    op.drop_index("ix_clover_payment_events_organization_created", table_name="clover_payment_events")
    op.drop_index("ix_clover_payment_events_installation_id", table_name="clover_payment_events")
    op.drop_index("ix_clover_payment_events_organization_id", table_name="clover_payment_events")
    op.drop_constraint("fk_clover_payment_events_tenant_order", "clover_payment_events", type_="foreignkey")
    op.drop_constraint("fk_clover_payment_events_tenant_installation", "clover_payment_events", type_="foreignkey")
    op.drop_constraint("uq_clover_payment_events_installation_payment", "clover_payment_events", type_="unique")
    op.create_unique_constraint("uq_clover_payment_events_environment_merchant_payment", "clover_payment_events", ["environment", "merchant_id", "payment_id"])
    op.drop_column("clover_payment_events", "installation_id")
    op.drop_column("clover_payment_events", "organization_id")
    op.drop_index("ix_orders_organization_clover_checkout", table_name="orders")
    op.drop_index("ix_orders_clover_installation_id", table_name="orders")
    op.drop_constraint("fk_orders_tenant_clover_installation", "orders", type_="foreignkey")
    op.drop_constraint("uq_orders_organization_clover_checkout_session", "orders", type_="unique")
    op.create_unique_constraint("uq_orders_clover_checkout_session_id", "orders", ["clover_checkout_session_id"])
    op.drop_constraint("ck_orders_clover_checkout_consistent", "orders", type_="check")
    op.create_check_constraint("ck_orders_clover_checkout_consistent", "orders", "(clover_merchant_id IS NULL AND clover_checkout_session_id IS NULL AND clover_checkout_url IS NULL AND clover_checkout_expires_at IS NULL) OR (clover_merchant_id IS NOT NULL AND clover_checkout_session_id IS NOT NULL AND clover_checkout_url IS NOT NULL AND clover_checkout_expires_at IS NOT NULL)")
    op.drop_column("orders", "clover_environment")
    op.drop_column("orders", "clover_installation_id")
    op.drop_index("ix_clover_installations_organization_state", table_name="clover_installations")
    op.drop_index("ix_clover_installations_organization_id", table_name="clover_installations")
    op.drop_constraint("uq_clover_installations_environment_merchant", "clover_installations", type_="unique")
    op.drop_constraint("uq_clover_installations_organization_environment", "clover_installations", type_="unique")
    op.drop_constraint("uq_clover_installations_organization_id_id", "clover_installations", type_="unique")
    op.drop_constraint("uq_clover_installations_tenant_identity", "clover_installations", type_="unique")
    op.drop_constraint("uq_clover_installations_id", "clover_installations", type_="unique")
    op.drop_constraint("fk_clover_installations_organization_id_organizations", "clover_installations", type_="foreignkey")
    op.drop_column("clover_installations", "page_config_uuid")
    op.drop_column("clover_installations", "organization_id")
    op.drop_column("clover_installations", "id")
