"""add individual staff PIN credentials

Revision ID: 20260807_14
Revises: 20260806_13
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260807_14"
down_revision: str | None = "20260806_13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_pin_credentials",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("verifier", sa.String(length=255), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["jds_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("staff_pin_credentials")
