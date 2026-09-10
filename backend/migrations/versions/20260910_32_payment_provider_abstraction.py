"""M1 payment provider abstraction: tenant settings + generic order payment fields.

Revision ID: 20260910_32
Revises: 20260903_31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260910_32"
down_revision: str | None = "20260903_31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_payment_settings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_key", sa.String(length=40), nullable=False),
        sa.Column("encrypted_config", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_org_payment_settings_organization",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("organization_id", name="pk_organization_payment_settings"),
        sa.CheckConstraint(
            "provider_key IN ('clover', 'stripe', 'square', 'moneris')",
            name="ck_org_payment_settings_provider_key",
        ),
    )
    op.create_index(
        "ix_org_payment_settings_provider",
        "organization_payment_settings",
        ["provider_key"],
    )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_key", sa.String(length=40), nullable=False),
        sa.Column("provider_event_id", sa.String(length=200), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("checkout_ref", sa.String(length=200), nullable=True),
        sa.Column("provider_payment_ref", sa.String(length=200), nullable=True),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("detail", sa.String(length=200), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "order_id"],
            ["orders.organization_id", "orders.id"],
            name="fk_payment_events_tenant_order",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payment_events"),
        sa.UniqueConstraint(
            "organization_id",
            "provider_key",
            "provider_event_id",
            name="uq_payment_events_org_provider_event",
        ),
    )
    op.create_index(
        "ix_payment_events_organization_id", "payment_events", ["organization_id"]
    )
    op.create_index(
        "ix_payment_events_provider_key", "payment_events", ["provider_key"]
    )
    op.create_index("ix_payment_events_order_id", "payment_events", ["order_id"])
    op.create_index(
        "ix_payment_events_organization_created",
        "payment_events",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_payment_events_organization_checkout",
        "payment_events",
        ["organization_id", "checkout_ref"],
    )

    op.add_column("orders", sa.Column("payment_provider", sa.String(length=40), nullable=True))
    op.add_column("orders", sa.Column("payment_status", sa.String(length=30), nullable=True))
    op.add_column(
        "orders", sa.Column("payment_checkout_ref", sa.String(length=200), nullable=True)
    )
    op.add_column("orders", sa.Column("payment_redirect_url", sa.Text(), nullable=True))
    op.add_column(
        "orders",
        sa.Column("payment_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("payment_provider_txn_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "orders", sa.Column("payment_failure_code", sa.String(length=80), nullable=True)
    )
    op.add_column(
        "orders",
        sa.Column("payment_paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column(
            "payment_provider_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_orders_payment_status_valid",
        "orders",
        "payment_status IS NULL OR payment_status IN "
        "('unpaid', 'pending', 'paid', 'failed', 'cancelled', 'refunded', 'manual_unpaid')",
    )
    op.create_index(
        "ix_orders_organization_payment_checkout",
        "orders",
        ["organization_id", "payment_checkout_ref"],
    )

    # Backfill generic fields from existing Clover checkout evidence (data-preserving).
    op.execute(
        """
        UPDATE orders
        SET
          payment_provider = 'clover',
          payment_status = CASE
            WHEN status = 'paid' THEN 'paid'
            WHEN status = 'payment_pending' THEN 'pending'
            WHEN status = 'payment_failed' THEN 'failed'
            ELSE 'unpaid'
          END,
          payment_checkout_ref = clover_checkout_session_id,
          payment_redirect_url = clover_checkout_url,
          payment_expires_at = clover_checkout_expires_at,
          payment_provider_metadata = jsonb_strip_nulls(
            jsonb_build_object(
              'environment', clover_environment,
              'merchant_id', clover_merchant_id,
              'installation_id', clover_installation_id::text
            )
          )
        WHERE clover_checkout_session_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE orders
        SET payment_status = CASE
          WHEN status = 'paid' THEN 'paid'
          WHEN status = 'payment_pending' THEN 'pending'
          WHEN status = 'payment_failed' THEN 'failed'
          ELSE COALESCE(payment_status, 'unpaid')
        END
        WHERE payment_status IS NULL
        """
    )

    # Tenants with a connected Clover installation get provider_key=clover.
    op.execute(
        """
        INSERT INTO organization_payment_settings (organization_id, provider_key)
        SELECT DISTINCT organization_id, 'clover'
        FROM clover_installations
        WHERE connection_state = 'connected'
        ON CONFLICT (organization_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_orders_organization_payment_checkout", table_name="orders")
    op.drop_constraint("ck_orders_payment_status_valid", "orders", type_="check")
    op.drop_column("orders", "payment_provider_metadata")
    op.drop_column("orders", "payment_paid_at")
    op.drop_column("orders", "payment_failure_code")
    op.drop_column("orders", "payment_provider_txn_id")
    op.drop_column("orders", "payment_expires_at")
    op.drop_column("orders", "payment_redirect_url")
    op.drop_column("orders", "payment_checkout_ref")
    op.drop_column("orders", "payment_status")
    op.drop_column("orders", "payment_provider")

    op.drop_index("ix_payment_events_organization_checkout", table_name="payment_events")
    op.drop_index("ix_payment_events_organization_created", table_name="payment_events")
    op.drop_index("ix_payment_events_order_id", table_name="payment_events")
    op.drop_index("ix_payment_events_provider_key", table_name="payment_events")
    op.drop_index("ix_payment_events_organization_id", table_name="payment_events")
    op.drop_table("payment_events")

    op.drop_index("ix_org_payment_settings_provider", table_name="organization_payment_settings")
    op.drop_table("organization_payment_settings")
