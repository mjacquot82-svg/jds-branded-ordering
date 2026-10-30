from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SquareInstallation(Base):
    """One Square seller connection per shop and environment. Tokens are encrypted."""

    __tablename__ = "square_installations"
    __table_args__ = (
        UniqueConstraint("organization_id", "environment", name="uq_square_installations_org_env"),
        UniqueConstraint("environment", "merchant_id", name="uq_square_installations_env_merchant"),
        Index("ix_square_installations_org_state", "organization_id", "connection_state"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    environment: Mapped[str] = mapped_column(String(20))
    merchant_id: Mapped[str] = mapped_column(String(100))
    application_id: Mapped[str] = mapped_column(String(100))
    location_id: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str | None] = mapped_column(String(3))
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    access_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    connection_state: Mapped[str] = mapped_column(
        String(30), default="connected", server_default="connected"
    )
    reconnect_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SquareOAuthState(Base):
    """Single-use OAuth state nonce (hash only)."""

    __tablename__ = "square_oauth_states"
    __table_args__ = (
        Index("ix_square_oauth_states_org_expires", "organization_id", "expires_at"),
    )

    nonce_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    membership_id: Mapped[UUID] = mapped_column()
    environment: Mapped[str] = mapped_column(String(20))
    application_id: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
