"""decouple modifier selection cardinality from quantity

Revision ID: 20260811_19
Revises: 20260811_18
"""
from alembic import op


revision = "20260811_19"
down_revision = "20260811_18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_modifier_groups_selection_range_valid",
        "modifier_groups",
        type_="check",
    )
    op.create_check_constraint(
        "ck_modifier_groups_selection_range_valid",
        "modifier_groups",
        "(selection_type <> 'single' OR allow_quantity OR maximum_selections = 1) "
        "AND (maximum_selections = 0 OR maximum_selections >= minimum_selections)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_modifier_groups_selection_range_valid",
        "modifier_groups",
        type_="check",
    )
    op.execute(
        "UPDATE modifier_groups SET maximum_selections = 1 "
        "WHERE selection_type = 'single' AND maximum_selections <> 1"
    )
    op.create_check_constraint(
        "ck_modifier_groups_selection_range_valid",
        "modifier_groups",
        "(selection_type = 'single' AND maximum_selections = 1) "
        "OR (selection_type = 'multiple' AND "
        "(maximum_selections = 0 OR maximum_selections >= minimum_selections))",
    )
