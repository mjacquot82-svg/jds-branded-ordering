"""add persistent authentication sessions

Revision ID: 20260804_08
Revises: 20260802_07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_08"
down_revision: str | None = "20260802_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "owner_sessions",
        sa.Column("is_persistent", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("owner_sessions", "is_persistent")
