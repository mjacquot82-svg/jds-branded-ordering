from datetime import datetime

from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CloverInstallation(Base):
    __tablename__ = "clover_installations"
    __table_args__ = (
        UniqueConstraint("id", name="uq_clover_installations_id"),
        UniqueConstraint("organization_id", "id", name="uq_clover_installations_organization_id_id"),
        UniqueConstraint(
            "organization_id", "id", "environment", "merchant_id",
            name="uq_clover_installations_tenant_identity",
        ),
        UniqueConstraint("organization_id", "environment", name="uq_clover_installations_organization_environment"),
        UniqueConstraint("environment", "merchant_id", name="uq_clover_installations_environment_merchant"),
        Index("ix_clover_installations_organization_state", "organization_id", "connection_state"),
    )

    id: Mapped[UUID] = mapped_column(default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    merchant_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    environment: Mapped[str] = mapped_column(String(20), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    access_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connection_state: Mapped[str] = mapped_column(
        String(30), default="connected", server_default="connected"
    )
    reconnect_reason: Mapped[str | None] = mapped_column(String(100))
    page_config_uuid: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CloverPaymentEvent(Base):
    __tablename__ = "clover_payment_events"
    __table_args__ = (
        UniqueConstraint(
            "installation_id", "payment_id",
            name="uq_clover_payment_events_installation_payment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "installation_id", "environment", "merchant_id"],
            [
                "clover_installations.organization_id",
                "clover_installations.id",
                "clover_installations.environment",
                "clover_installations.merchant_id",
            ],
            name="fk_clover_payment_events_tenant_installation", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "order_id"], ["orders.organization_id", "orders.id"],
            name="fk_clover_payment_events_tenant_order", ondelete="RESTRICT",
        ),
        Index("ix_clover_payment_events_organization_created", "organization_id", "created_at"),
        Index("ix_clover_payment_events_organization_checkout", "organization_id", "checkout_session_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(index=True)
    installation_id: Mapped[UUID] = mapped_column(index=True)
    environment: Mapped[str] = mapped_column(String(20), index=True)
    merchant_id: Mapped[str] = mapped_column(String(100), index=True)
    payment_id: Mapped[str] = mapped_column(String(200))
    checkout_session_id: Mapped[str] = mapped_column(String(200), index=True)
    order_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    source: Mapped[str] = mapped_column(String(30))
    webhook_payload_sha256: Mapped[str | None] = mapped_column(String(64))
    reported_status: Mapped[str | None] = mapped_column(String(30))
    verified_status: Mapped[str | None] = mapped_column(String(30))
    verified_amount_cents: Mapped[int | None] = mapped_column(Integer)
    verified_currency: Mapped[str | None] = mapped_column(String(3))
    outcome: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CloverOAuthState(Base):
    __tablename__ = "clover_oauth_states"
    __table_args__ = (
        Index("ix_clover_oauth_states_organization_expires", "organization_id", "expires_at"),
    )

    nonce_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    membership_id: Mapped[UUID] = mapped_column(ForeignKey("organization_memberships.id", ondelete="CASCADE"))
    environment: Mapped[str] = mapped_column(String(20))
    app_id: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
