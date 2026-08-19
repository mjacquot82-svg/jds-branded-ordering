"""add configurable customer loyalty ledger

Revision ID: 20260810_16
Revises: 20260809_15
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_16"
down_revision: str | None = "20260809_15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("loyalty_programs",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False), sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("stamps_required", sa.Integer(), server_default="6", nullable=False), sa.Column("reward_description", sa.String(200), nullable=False),
        sa.Column("earning_rule", sa.String(60), server_default="one_per_completed_qualifying_order", nullable=False),
        sa.Column("reward_type", sa.String(60), server_default="free_qualifying_product", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_loyalty_programs_organization_slug"),
        sa.CheckConstraint("stamps_required > 0", name="ck_loyalty_programs_stamps_required_positive"),
        sa.CheckConstraint("earning_rule = 'one_per_completed_qualifying_order'", name="ck_loyalty_programs_earning_rule_valid"),
        sa.CheckConstraint("reward_type = 'free_qualifying_product'", name="ck_loyalty_programs_reward_type_valid"))
    op.create_index("ix_loyalty_programs_organization_id", "loyalty_programs", ["organization_id"])
    op.create_index("ix_loyalty_programs_enabled", "loyalty_programs", ["enabled"])
    op.create_table("loyalty_program_products",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("loyalty_program_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.BigInteger()), sa.Column("earning_eligible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("reward_eligible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["loyalty_program_id"], ["loyalty_programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("loyalty_program_id", "product_id", name="uq_loyalty_program_products_program_product"),
        sa.CheckConstraint("earning_eligible OR reward_eligible", name="ck_loyalty_program_products_some_eligibility_required"))
    op.create_index("ix_loyalty_program_products_loyalty_program_id", "loyalty_program_products", ["loyalty_program_id"])
    op.create_index("ix_loyalty_program_products_product_id", "loyalty_program_products", ["product_id"])
    op.create_table("customer_loyalty_events",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("customer_user_id", sa.Uuid(), nullable=False),
        sa.Column("loyalty_program_id", sa.Uuid(), nullable=False), sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("related_order_id", sa.BigInteger()),
        sa.Column("actor_user_id", sa.Uuid()), sa.Column("reason", sa.Text()), sa.Column("threshold_snapshot", sa.Integer()),
        sa.Column("program_name_snapshot", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["customer_user_id"], ["jds_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["loyalty_program_id"], ["loyalty_programs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["related_order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["jds_users.id"], ondelete="SET NULL"),
        sa.CheckConstraint("event_type IN ('stamp_earned','reward_earned','reward_redeemed','manual_adjustment','reversal')", name="ck_customer_loyalty_events_event_type_valid"),
        sa.CheckConstraint("quantity <> 0", name="ck_customer_loyalty_events_quantity_nonzero"),
        sa.CheckConstraint("threshold_snapshot IS NULL OR threshold_snapshot > 0", name="ck_customer_loyalty_events_threshold_snapshot_positive"),
        sa.CheckConstraint("event_type NOT IN ('manual_adjustment','reversal') OR (actor_user_id IS NOT NULL AND reason IS NOT NULL AND btrim(reason) <> '')", name="ck_customer_loyalty_events_manual_audit_required"),
        sa.CheckConstraint("event_type <> 'stamp_earned' OR (quantity = 1 AND related_order_id IS NOT NULL)", name="ck_customer_loyalty_events_stamp_earned_shape_valid"),
        sa.CheckConstraint("event_type <> 'reward_earned' OR (quantity > 0 AND threshold_snapshot IS NOT NULL)", name="ck_customer_loyalty_events_reward_earned_shape_valid"),
        sa.CheckConstraint("event_type <> 'reward_redeemed' OR quantity > 0", name="ck_customer_loyalty_events_reward_redeemed_quantity_positive"),
        sa.CheckConstraint("event_type = 'reward_earned' OR threshold_snapshot IS NULL", name="ck_customer_loyalty_events_threshold_snapshot_event_valid"))
    for column in ("customer_user_id", "loyalty_program_id", "event_type", "related_order_id", "actor_user_id", "created_at"):
        op.create_index(f"ix_customer_loyalty_events_{column}", "customer_loyalty_events", [column])
    op.create_index("uq_loyalty_order_stamp", "customer_loyalty_events", ["loyalty_program_id", "related_order_id"], unique=True, postgresql_where=sa.text("event_type = 'stamp_earned' AND related_order_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_table("customer_loyalty_events")
    op.drop_table("loyalty_program_products")
    op.drop_table("loyalty_programs")
