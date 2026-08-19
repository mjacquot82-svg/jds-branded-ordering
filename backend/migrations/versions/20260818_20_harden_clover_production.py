"""harden Clover token lifecycle and payment evidence

Revision ID: 20260818_20
Revises: 20260811_19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_20"
down_revision: str | None = "20260811_19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clover_installations",
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "clover_installations",
        sa.Column(
            "connection_state",
            sa.String(length=30),
            nullable=False,
            server_default="connected",
        ),
    )
    op.add_column(
        "clover_installations",
        sa.Column("reconnect_reason", sa.String(length=100), nullable=True),
    )
    # Existing installations predate refresh-expiry persistence. They remain usable,
    # but must reconnect before production so expiry is known authoritatively.
    op.execute(
        "UPDATE clover_installations SET connection_state = 'reconnect_required', "
        "reconnect_reason = 'refresh_expiration_unknown' "
        "WHERE environment = 'production'"
    )

    op.create_table(
        "clover_payment_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("merchant_id", sa.String(length=100), nullable=False),
        sa.Column("payment_id", sa.String(length=200), nullable=False),
        sa.Column("checkout_session_id", sa.String(length=200), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("webhook_payload_sha256", sa.String(length=64), nullable=True),
        sa.Column("reported_status", sa.String(length=30), nullable=True),
        sa.Column("verified_status", sa.String(length=30), nullable=True),
        sa.Column("verified_amount_cents", sa.Integer(), nullable=True),
        sa.Column("verified_currency", sa.String(length=3), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("detail", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clover_payment_events"),
        sa.UniqueConstraint(
            "environment", "merchant_id", "payment_id",
            name="uq_clover_payment_events_environment_merchant_payment",
        ),
    )
    op.create_index(
        "ix_clover_payment_events_environment",
        "clover_payment_events",
        ["environment"],
    )
    op.create_index(
        "ix_clover_payment_events_merchant_id",
        "clover_payment_events",
        ["merchant_id"],
    )
    op.create_index(
        "ix_clover_payment_events_checkout_session_id",
        "clover_payment_events",
        ["checkout_session_id"],
    )
    op.create_index(
        "ix_clover_payment_events_order_id",
        "clover_payment_events",
        ["order_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_clover_payment_events_order_id", table_name="clover_payment_events")
    op.drop_index(
        "ix_clover_payment_events_checkout_session_id",
        table_name="clover_payment_events",
    )
    op.drop_index("ix_clover_payment_events_merchant_id", table_name="clover_payment_events")
    op.drop_index("ix_clover_payment_events_environment", table_name="clover_payment_events")
    op.drop_table("clover_payment_events")
    op.drop_column("clover_installations", "reconnect_reason")
    op.drop_column("clover_installations", "connection_state")
    op.drop_column("clover_installations", "refresh_token_expires_at")
