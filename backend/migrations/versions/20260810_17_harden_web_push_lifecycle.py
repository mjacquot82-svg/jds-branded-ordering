"""harden web push lifecycle

Revision ID: 20260810_17
Revises: 20260810_16
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_17"
down_revision: str | None = "20260810_16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("push_announcements", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.create_index("ix_push_announcements_expires_at", "push_announcements", ["expires_at"])
    op.execute(
        "UPDATE push_announcements SET expires_at = created_at + interval '4 hours' "
        "WHERE kind = 'general' AND expires_at IS NULL"
    )
    op.add_column(
        "push_announcements",
        sa.Column("suppressed_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.drop_constraint(
        "ck_push_announcements_counts_nonnegative",
        "push_announcements",
        type_="check",
    )
    op.create_check_constraint(
        "ck_push_announcements_counts_nonnegative",
        "push_announcements",
        "attempted_count >= 0 AND accepted_count >= 0 AND failed_count >= 0 "
        "AND expired_count >= 0 AND suppressed_count >= 0 AND clicked_count >= 0",
    )
    op.drop_constraint(
        "ck_push_delivery_attempts_status_valid",
        "push_delivery_attempts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_push_delivery_attempts_status_valid",
        "push_delivery_attempts",
        "status IN ('queued', 'claimed', 'retry', 'accepted', 'failed', 'expired', 'suppressed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_push_delivery_attempts_status_valid",
        "push_delivery_attempts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_push_delivery_attempts_status_valid",
        "push_delivery_attempts",
        "status IN ('queued', 'claimed', 'retry', 'accepted', 'failed', 'expired')",
    )
    op.drop_constraint(
        "ck_push_announcements_counts_nonnegative",
        "push_announcements",
        type_="check",
    )
    op.create_check_constraint(
        "ck_push_announcements_counts_nonnegative",
        "push_announcements",
        "attempted_count >= 0 AND accepted_count >= 0 AND failed_count >= 0 "
        "AND expired_count >= 0 AND clicked_count >= 0",
    )
    op.drop_column("push_announcements", "suppressed_count")
    op.drop_index("ix_push_announcements_expires_at", table_name="push_announcements")
    op.drop_column("push_announcements", "expires_at")
