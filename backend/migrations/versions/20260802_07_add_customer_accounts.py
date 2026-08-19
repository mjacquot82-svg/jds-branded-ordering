"""add customer accounts and order ownership

Revision ID: 20260802_07
Revises: 20260802_06
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260802_07"
down_revision: str | None = "20260802_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.String(30), server_default="", nullable=False),
        sa.Column("preferred_pickup_minutes", sa.Integer()),
        sa.Column("preferred_pickup_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("preferred_pickup_minutes IS NULL OR preferred_pickup_minutes >= 0", name="ck_customer_profiles_preferred_pickup_nonnegative"),
        sa.ForeignKeyConstraint(["user_id"], ["jds_users.id"], name="fk_customer_profiles_user_id_jds_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name="pk_customer_profiles"),
    )
    op.add_column("orders", sa.Column("customer_user_id", sa.Uuid()))
    op.create_foreign_key("fk_orders_customer_user_id_jds_users", "orders", "jds_users", ["customer_user_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_orders_customer_user_id", "orders", ["customer_user_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_customer_user_id", table_name="orders")
    op.drop_constraint("fk_orders_customer_user_id_jds_users", "orders", type_="foreignkey")
    op.drop_column("orders", "customer_user_id")
    op.drop_table("customer_profiles")
