from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CloverInstallation(Base):
    __tablename__ = "clover_installations"

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
            "environment", "merchant_id", "payment_id",
            name="uq_clover_payment_events_environment_merchant_payment",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
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
