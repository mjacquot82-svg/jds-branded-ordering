"""add direct web push persistence

Revision ID: 20260809_15
Revises: 20260807_14
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260809_15"
down_revision: str | None = "20260807_14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table("customer_notification_preferences",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("customer_user_id", sa.Uuid(), nullable=False),
        sa.Column("notification_kind", sa.String(40), nullable=False), sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True)), sa.Column("disabled_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["customer_user_id"], ["jds_users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("notification_kind = 'lunch_special'", name="ck_customer_notification_preferences_kind_valid"),
        sa.UniqueConstraint("customer_user_id", "notification_kind", name="uq_customer_notification_preference"))
    op.create_index("ix_customer_notification_preferences_customer_user_id", "customer_notification_preferences", ["customer_user_id"])
    op.create_table("web_push_subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("customer_user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_ciphertext", sa.LargeBinary(), nullable=False), sa.Column("endpoint_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("p256dh_ciphertext", sa.LargeBinary(), nullable=False), sa.Column("auth_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("content_encoding", sa.String(30), server_default="aes128gcm", nullable=False), sa.Column("device_label", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True)), sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("expired_at", sa.DateTime(timezone=True)), sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["customer_user_id"], ["jds_users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("content_encoding = 'aes128gcm'", name="ck_web_push_subscriptions_encoding_valid"),
        sa.CheckConstraint("failure_count >= 0", name="ck_web_push_subscriptions_failure_count_nonnegative"))
    for col in ("customer_user_id", "expired_at", "revoked_at"): op.create_index(f"ix_web_push_subscriptions_{col}", "web_push_subscriptions", [col])
    op.create_table("push_announcements",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False), sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(80), nullable=False), sa.Column("frozen_message", sa.String(280), nullable=False), sa.Column("target_route", sa.String(300), nullable=False),
        sa.Column("source_product_id", sa.BigInteger()), sa.Column("product_name_snapshot", sa.String(200)), sa.Column("price_cents_snapshot", sa.Integer()),
        sa.Column("actor_user_id", sa.Uuid()), sa.Column("actor_name_snapshot", sa.String(200), nullable=False), sa.Column("status", sa.String(30), server_default="queued", nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False), sa.Column("cafe_day", sa.Date()), sa.Column("is_override", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("attempted_count", sa.Integer(), server_default="0", nullable=False), sa.Column("accepted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False), sa.Column("expired_count", sa.Integer(), server_default="0", nullable=False), sa.Column("clicked_count", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["source_product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["jds_users.id"], ondelete="SET NULL"), sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_push_announcement_idempotency"),
        sa.CheckConstraint("kind IN ('lunch_special', 'general')", name="ck_push_announcements_kind_valid"),
        sa.CheckConstraint("status IN ('queued', 'attempting', 'completed')", name="ck_push_announcements_status_valid"),
        sa.CheckConstraint("attempted_count >= 0 AND accepted_count >= 0 AND failed_count >= 0 AND expired_count >= 0 AND clicked_count >= 0", name="ck_push_announcements_counts_nonnegative"))
    for col in ("organization_id", "kind", "cafe_day", "created_at"): op.create_index(f"ix_push_announcements_{col}", "push_announcements", [col])
    op.create_index("uq_push_lunch_day_standard", "push_announcements", ["organization_id", "cafe_day"], unique=True,
                    postgresql_where=sa.text("kind = 'lunch_special' AND is_override IS FALSE"))
    op.create_table("push_delivery_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("announcement_id", sa.Uuid(), nullable=False), sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(30), server_default="queued", nullable=False), sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("provider_http_status", sa.Integer()), sa.Column("error_code", sa.String(80)),
        sa.ForeignKeyConstraint(["announcement_id"], ["push_announcements.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["subscription_id"], ["web_push_subscriptions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("announcement_id", "subscription_id", name="uq_push_delivery_announcement_subscription"),
        sa.CheckConstraint("status IN ('queued', 'claimed', 'retry', 'accepted', 'failed', 'expired')", name="ck_push_delivery_attempts_status_valid"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_push_delivery_attempts_attempt_count_nonnegative"))
    for col in ("announcement_id", "subscription_id", "status", "next_attempt_at", "claimed_at"): op.create_index(f"ix_push_delivery_attempts_{col}", "push_delivery_attempts", [col])

def downgrade() -> None:
    op.drop_table("push_delivery_attempts"); op.drop_index("uq_push_lunch_day_standard", table_name="push_announcements")
    op.drop_table("push_announcements"); op.drop_table("web_push_subscriptions"); op.drop_table("customer_notification_preferences")
