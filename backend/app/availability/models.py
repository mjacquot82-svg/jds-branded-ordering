from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base

if TYPE_CHECKING:
    from app.catalog.models import Product


class AvailabilityModelValidation:
    @validates("minimum_lead_time_minutes")
    def validate_lead_time(self, _: str, value: int) -> int:
        if value < 0:
            raise ValueError("minimum_lead_time_minutes must be nonnegative.")
        return value

    @validates("pickup_interval_minutes")
    def validate_pickup_interval(self, _: str, value: int) -> int:
        if not 1 <= value <= 1440:
            raise ValueError(
                "pickup_interval_minutes must be between 1 and 1440."
            )
        return value

    @validates("maximum_advance_days")
    def validate_advance_days(self, _: str, value: int) -> int:
        if not 1 <= value <= 365:
            raise ValueError("maximum_advance_days must be between 1 and 365.")
        return value

    @validates("reason")
    def validate_reason(self, _: str, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must not be blank.")
        return normalized


class BusinessSettings(AvailabilityModelValidation, Base):
    __tablename__ = "business_settings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", name="uq_business_settings_organization_id"
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_business_settings_organization_id_id"
        ),
        CheckConstraint("btrim(timezone) <> ''", name="timezone_nonblank"),
        CheckConstraint(
            "ordering_mode IN ('schedule', 'force_open', 'force_closed')",
            name="ordering_mode_valid",
        ),
        CheckConstraint(
            "minimum_lead_time_minutes >= 0",
            name="lead_time_nonnegative",
        ),
        CheckConstraint(
            "pickup_interval_minutes BETWEEN 1 AND 1440",
            name="pickup_interval_valid",
        ),
        CheckConstraint(
            "maximum_advance_days BETWEEN 1 AND 365",
            name="advance_days_valid",
        ),
        CheckConstraint("btrim(tax_name) <> ''", name="tax_name_nonblank"),
        CheckConstraint(
            "tax_rate_millionths BETWEEN 0 AND 10000000",
            name="tax_rate_millionths_valid",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    timezone: Mapped[str] = mapped_column(String(100))
    ordering_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )
    ordering_mode: Mapped[str] = mapped_column(
        String(20), default="schedule", server_default="schedule"
    )
    minimum_lead_time_minutes: Mapped[int] = mapped_column(
        Integer,
        default=15,
        server_default="15",
    )
    pickup_interval_minutes: Mapped[int] = mapped_column(
        Integer,
        default=5,
        server_default="5",
    )
    maximum_advance_days: Mapped[int] = mapped_column(
        Integer,
        default=14,
        server_default="14",
    )
    tax_name: Mapped[str] = mapped_column(
        String(50), default="HST", server_default="HST"
    )
    tax_rate_millionths: Mapped[int] = mapped_column(
        Integer, default=1_300_000, server_default="1300000"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    hours: Mapped[list[BusinessHour]] = relationship(
        back_populates="settings",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    closures: Mapped[list[BusinessClosure]] = relationship(
        back_populates="settings",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @validates("timezone", "tax_name")
    def validate_nonblank_setting(self, _: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("timezone must not be blank.")
        return normalized

    @validates("ordering_mode")
    def validate_ordering_mode(self, _: str, value: str) -> str:
        if value not in {"schedule", "force_open", "force_closed"}:
            raise ValueError("ordering_mode is invalid.")
        return value


class BusinessHour(Base):
    __tablename__ = "business_hours"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "weekday",
            name="uq_business_hours_organization_weekday",
        ),
        ForeignKeyConstraint(
            ["organization_id", "business_settings_id"],
            ["business_settings.organization_id", "business_settings.id"],
            name="fk_business_hours_organization_settings",
            ondelete="CASCADE",
        ),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_valid"),
        CheckConstraint(
            "(is_closed AND opens_at IS NULL AND closes_at IS NULL) OR "
            "(NOT is_closed AND opens_at IS NOT NULL AND closes_at IS NOT NULL "
            "AND opens_at < closes_at)",
            name="period_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    business_settings_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)
    is_closed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    opens_at: Mapped[time | None] = mapped_column(Time(timezone=False))
    closes_at: Mapped[time | None] = mapped_column(Time(timezone=False))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    settings: Mapped[BusinessSettings] = relationship(back_populates="hours")

    @validates("weekday")
    def validate_weekday(self, _: str, value: int) -> int:
        if not 0 <= value <= 6:
            raise ValueError("weekday must be between zero and six.")
        return value

    def validate_period(self) -> None:
        if self.is_closed:
            if self.opens_at is not None or self.closes_at is not None:
                raise ValueError("closed business days must not define hours.")
            return
        if self.opens_at is None or self.closes_at is None:
            raise ValueError("open business days require opening and closing times.")
        if self.opens_at >= self.closes_at:
            raise ValueError("opening time must be before closing time.")


class BusinessClosure(AvailabilityModelValidation, Base):
    __tablename__ = "business_closures"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "business_date",
            name="uq_business_closures_organization_date",
        ),
        ForeignKeyConstraint(
            ["organization_id", "business_settings_id"],
            ["business_settings.organization_id", "business_settings.id"],
            name="fk_business_closures_organization_settings",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "reason IS NULL OR btrim(reason) <> ''", name="reason_nonblank"
        ),
        CheckConstraint(
            "reopens_on IS NULL OR reopens_on > business_date",
            name="reopens_after_start",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    business_settings_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )
    business_date: Mapped[date] = mapped_column(Date)
    reopens_on: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    settings: Mapped[BusinessSettings] = relationship(back_populates="closures")


class ProductAvailability(AvailabilityModelValidation, Base):
    __tablename__ = "product_availability"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            name="fk_product_availability_organization_product",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "reason IS NULL OR btrim(reason) <> ''", name="reason_nonblank"
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    default_available: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped[Product] = relationship(back_populates="availability")


class ProductAvailabilityOverride(AvailabilityModelValidation, Base):
    __tablename__ = "product_availability_overrides"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "product_id",
            "business_date",
            name="uq_product_availability_overrides_organization_product_date",
        ),
        ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            name="fk_product_availability_overrides_organization_product",
            ondelete="CASCADE",
        ),
        Index(
            "ix_product_availability_overrides_organization_date",
            "organization_id",
            "business_date",
        ),
        CheckConstraint(
            "reason IS NULL OR btrim(reason) <> ''", name="reason_nonblank"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )
    business_date: Mapped[date] = mapped_column(Date)
    is_available: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped[Product] = relationship(
        back_populates="availability_overrides"
    )


@event.listens_for(BusinessHour, "before_insert")
@event.listens_for(BusinessHour, "before_update")
def validate_business_hour_period(
    _: object,
    __: object,
    business_hour: BusinessHour,
) -> None:
    business_hour.validate_period()
