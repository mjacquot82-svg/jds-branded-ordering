from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerProfile(Base):
    __tablename__ = "customer_profiles"
    __table_args__ = (
        CheckConstraint("preferred_pickup_minutes IS NULL OR preferred_pickup_minutes >= 0", name="preferred_pickup_nonnegative"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("jds_users.id", ondelete="CASCADE"), primary_key=True)
    phone: Mapped[str] = mapped_column(String(30), default="", server_default="")
    preferred_pickup_minutes: Mapped[int | None] = mapped_column(Integer)
    preferred_pickup_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
