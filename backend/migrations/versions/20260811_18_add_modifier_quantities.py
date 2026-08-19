"""add modifier quantity capability

Revision ID: 20260811_18
Revises: 20260810_17
"""
from alembic import op
import sqlalchemy as sa

revision = "20260811_18"
down_revision = "20260810_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("modifier_groups", sa.Column("allow_quantity", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("order_item_modifiers", sa.Column("quantity", sa.Integer(), server_default="1", nullable=False))
    op.create_check_constraint("ck_order_item_modifiers_quantity_positive", "order_item_modifiers", "quantity >= 1")


def downgrade() -> None:
    op.drop_constraint("ck_order_item_modifiers_quantity_positive", "order_item_modifiers", type_="check")
    op.drop_column("order_item_modifiers", "quantity")
    op.drop_column("modifier_groups", "allow_quantity")
