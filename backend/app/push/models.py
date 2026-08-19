from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, LargeBinary, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class CustomerNotificationPreference(Base):
    __tablename__ = "customer_notification_preferences"
    __table_args__ = (
        UniqueConstraint("organization_id", "customer_user_id", "notification_kind", name="uq_customer_notification_preference"),
        CheckConstraint("notification_kind = 'lunch_special'", name="ck_customer_notification_preferences_kind_valid"),
        ForeignKeyConstraint(
            ["organization_id", "customer_user_id"],
            ["organization_customers.organization_id", "organization_customers.user_id"],
            name="fk_customer_notification_preferences_org_customer", ondelete="CASCADE",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    customer_user_id: Mapped[UUID] = mapped_column(ForeignKey("jds_users.id", ondelete="CASCADE"), index=True)
    notification_kind: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WebPushSubscription(Base):
    __tablename__ = "web_push_subscriptions"
    __table_args__ = (
        CheckConstraint("content_encoding = 'aes128gcm'", name="ck_web_push_subscriptions_encoding_valid"),
        CheckConstraint("failure_count >= 0", name="ck_web_push_subscriptions_failure_count_nonnegative"),
        UniqueConstraint("organization_id", "endpoint_fingerprint", name="uq_web_push_subscription_org_endpoint"),
        UniqueConstraint("organization_id", "id", name="uq_web_push_subscriptions_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "customer_user_id"],
            ["organization_customers.organization_id", "organization_customers.user_id"],
            name="fk_web_push_subscriptions_org_customer", ondelete="CASCADE",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    customer_user_id: Mapped[UUID] = mapped_column(ForeignKey("jds_users.id", ondelete="CASCADE"), index=True)
    endpoint_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    endpoint_fingerprint: Mapped[str] = mapped_column(String(64))
    p256dh_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    auth_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    content_encoding: Mapped[str] = mapped_column(String(30), default="aes128gcm", server_default="aes128gcm")
    device_label: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class PushAnnouncement(Base):
    __tablename__ = "push_announcements"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_push_announcement_idempotency"),
        UniqueConstraint("organization_id", "id", name="uq_push_announcements_org_id"),
        Index("uq_push_lunch_day_standard", "organization_id", "cafe_day", unique=True, postgresql_where=text("kind = 'lunch_special' AND is_override IS FALSE")),
        CheckConstraint("kind IN ('lunch_special', 'general')", name="ck_push_announcements_kind_valid"),
        CheckConstraint("status IN ('queued', 'attempting', 'completed')", name="ck_push_announcements_status_valid"),
        CheckConstraint("attempted_count >= 0 AND accepted_count >= 0 AND failed_count >= 0 AND expired_count >= 0 AND suppressed_count >= 0 AND clicked_count >= 0", name="ck_push_announcements_counts_nonnegative"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(80))
    frozen_message: Mapped[str] = mapped_column(String(280))
    target_route: Mapped[str] = mapped_column(String(300))
    source_product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    product_name_snapshot: Mapped[str | None] = mapped_column(String(200))
    price_cents_snapshot: Mapped[int | None] = mapped_column(Integer)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("jds_users.id", ondelete="SET NULL"))
    actor_name_snapshot: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="queued", server_default="queued")
    idempotency_key: Mapped[str] = mapped_column(String(100))
    cafe_day: Mapped[date | None] = mapped_column(Date, index=True)
    is_override: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempted_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    accepted_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expired_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    suppressed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    clicked_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class PushDeliveryAttempt(Base):
    __tablename__ = "push_delivery_attempts"
    __table_args__ = (
        UniqueConstraint("announcement_id", "subscription_id", name="uq_push_delivery_announcement_subscription"),
        CheckConstraint("status IN ('queued', 'claimed', 'retry', 'accepted', 'failed', 'expired', 'suppressed')", name="ck_push_delivery_attempts_status_valid"),
        CheckConstraint("attempt_count >= 0", name="ck_push_delivery_attempts_attempt_count_nonnegative"),
        ForeignKeyConstraint(
            ["organization_id", "announcement_id"],
            ["push_announcements.organization_id", "push_announcements.id"],
            name="fk_push_delivery_attempts_org_announcement", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "subscription_id"],
            ["web_push_subscriptions.organization_id", "web_push_subscriptions.id"],
            name="fk_push_delivery_attempts_org_subscription", ondelete="CASCADE",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    announcement_id: Mapped[UUID] = mapped_column(ForeignKey("push_announcements.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[UUID] = mapped_column(ForeignKey("web_push_subscriptions.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", server_default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_http_status: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
