from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.availability.models import BusinessHour, BusinessSettings
from app.availability.repository import AvailabilityRepositoryProtocol


class AvailabilityConfigurationError(RuntimeError):
    """Raised when persisted business rules are missing or invalid."""


class PickupValidationCode(str, Enum):
    VALID = "valid"
    ORDERING_DISABLED = "ordering_disabled"
    PAST = "past"
    LEAD_TIME = "lead_time"
    TOO_FAR_AHEAD = "too_far_ahead"
    CLOSED_DATE = "closed_date"
    CLOSED_DAY = "closed_day"
    OUTSIDE_HOURS = "outside_hours"
    INTERVAL = "interval"


@dataclass(frozen=True)
class PickupValidation:
    is_valid: bool
    code: PickupValidationCode
    requested_at: datetime
    message: str | None = None


@dataclass(frozen=True)
class QuickPickupOption:
    key: str
    label: str
    requested_at: datetime
    preference_minutes: int | None = None


@dataclass(frozen=True)
class SchedulingOptions:
    server_now: datetime
    business_timezone: str
    ordering_available: bool
    ordering_status: str
    ordering_mode: str
    shop_open: bool
    status_reason: str | None
    unavailable_reason: str | None
    minimum_lead_time_minutes: int
    pickup_interval_minutes: int
    maximum_advance_days: int
    earliest_pickup_at: datetime | None
    quick_pickup_options: tuple[QuickPickupOption, ...]
    custom_pickup_at: datetime | None = None
    custom_pickup_error: str | None = None


@dataclass(frozen=True)
class Sellability:
    is_sellable: bool
    product_id: int
    business_date: date
    reason: str | None = None


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone information.")


def _business_timezone(settings: BusinessSettings) -> ZoneInfo:
    try:
        return ZoneInfo(settings.timezone)
    except ZoneInfoNotFoundError as error:
        raise AvailabilityConfigurationError(
            f"Unknown business timezone: {settings.timezone}."
        ) from error


def _round_forward(value: datetime, interval_minutes: int) -> datetime:
    day_start = value.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed_minutes = (value - day_start).total_seconds() / 60
    rounded_minutes = int(elapsed_minutes // interval_minutes) * interval_minutes
    if rounded_minutes < elapsed_minutes:
        rounded_minutes += interval_minutes
    return day_start + timedelta(minutes=rounded_minutes)


class PickupSchedulingService:
    QUICK_PICKUP_PREFERENCES = (10, 20, 30, 60)

    def __init__(self, repository: AvailabilityRepositoryProtocol) -> None:
        self._repository = repository

    def validate(
        self,
        requested_at: datetime,
        *,
        now: datetime,
    ) -> PickupValidation:
        _require_aware(requested_at, "requested_at")
        _require_aware(now, "now")
        settings = self._settings()
        timezone = _business_timezone(settings)
        local_now = now.astimezone(timezone)
        local_requested = requested_at.astimezone(timezone)

        accepting_orders, _, _, _ = self._current_state(settings, local_now)
        if not accepting_orders:
            return self._invalid(
                PickupValidationCode.ORDERING_DISABLED,
                local_requested,
                "Online ordering is currently disabled.",
            )
        if local_requested < local_now:
            return self._invalid(
                PickupValidationCode.PAST,
                local_requested,
                "Pickup time must not be in the past.",
            )
        if local_requested < local_now + timedelta(
            minutes=settings.minimum_lead_time_minutes
        ):
            return self._invalid(
                PickupValidationCode.LEAD_TIME,
                local_requested,
                "Pickup time does not meet the minimum lead time.",
            )
        if (
            local_requested.date()
            > local_now.date() + timedelta(days=settings.maximum_advance_days)
        ):
            return self._invalid(
                PickupValidationCode.TOO_FAR_AHEAD,
                local_requested,
                "Pickup time is beyond the scheduling horizon.",
            )
        if self._repository.get_business_closure(local_requested.date()):
            return self._invalid(
                PickupValidationCode.CLOSED_DATE,
                local_requested,
                "The business is closed on the requested date.",
            )

        hours = self._repository.get_business_hour(local_requested.weekday())
        if hours is None or hours.is_closed:
            return self._invalid(
                PickupValidationCode.CLOSED_DAY,
                local_requested,
                "The business is closed on the requested weekday.",
            )
        if not self._inside_hours(local_requested, hours):
            return self._invalid(
                PickupValidationCode.OUTSIDE_HOURS,
                local_requested,
                "Pickup time is outside business hours.",
            )
        minutes_since_midnight = (
            local_requested.hour * 60 + local_requested.minute
        )
        if (
            local_requested.second != 0
            or local_requested.microsecond != 0
            or minutes_since_midnight % settings.pickup_interval_minutes != 0
        ):
            return self._invalid(
                PickupValidationCode.INTERVAL,
                local_requested,
                "Pickup time is not aligned to the scheduling interval.",
            )

        return PickupValidation(
            is_valid=True,
            code=PickupValidationCode.VALID,
            requested_at=local_requested,
        )

    def earliest_pickup(self, *, now: datetime) -> datetime | None:
        _require_aware(now, "now")
        settings = self._settings()
        if self._ordering_mode(settings) == "force_closed":
            return None

        timezone = _business_timezone(settings)
        local_now = now.astimezone(timezone)
        return self._earliest_scheduled_pickup(local_now, settings)

    def _earliest_scheduled_pickup(
        self,
        local_now: datetime,
        settings: BusinessSettings,
    ) -> datetime | None:
        candidate = _round_forward(
            local_now + timedelta(minutes=settings.minimum_lead_time_minutes),
            settings.pickup_interval_minutes,
        )
        last_date = local_now.date() + timedelta(
            days=settings.maximum_advance_days
        )

        while candidate.date() <= last_date:
            if self._repository.get_business_closure(candidate.date()):
                candidate = self._next_day(candidate)
                continue

            hours = self._repository.get_business_hour(candidate.weekday())
            if hours is None or hours.is_closed:
                candidate = self._next_day(candidate)
                continue

            assert hours.opens_at is not None
            assert hours.closes_at is not None
            opens_at = datetime.combine(
                candidate.date(),
                hours.opens_at,
                tzinfo=local_now.tzinfo,
            )
            closes_at = datetime.combine(
                candidate.date(),
                hours.closes_at,
                tzinfo=local_now.tzinfo,
            )
            candidate = _round_forward(
                max(candidate, opens_at),
                settings.pickup_interval_minutes,
            )
            if candidate < closes_at:
                return candidate

            candidate = self._next_day(candidate)

        return None

    def options(
        self,
        *,
        now: datetime,
        custom_pickup_time: time | None = None,
    ) -> SchedulingOptions:
        """Build customer pickup choices from the authoritative business rules."""
        _require_aware(now, "now")
        settings = self._settings()
        timezone = _business_timezone(settings)
        local_now = now.astimezone(timezone)
        accepting_orders, shop_open, ordering_status, status_reason = self._current_state(
            settings, local_now
        )
        earliest = self._earliest_scheduled_pickup(local_now, settings)

        if not accepting_orders:
            if ordering_status == "paused":
                earliest = None
            elif earliest is None:
                status_reason = "No pickup times are currently available."
            return self._options_unavailable(
                local_now,
                settings,
                status_reason or "Online ordering is currently unavailable.",
                ordering_status=ordering_status,
                shop_open=shop_open,
                earliest_pickup_at=earliest,
            )

        if earliest is None:
            return self._options_unavailable(
                local_now,
                settings,
                "No pickup times are currently available.",
                ordering_status="closed",
                shop_open=shop_open,
            )

        options = [QuickPickupOption("asap", "ASAP", earliest)]
        seen = {earliest}
        for minutes in self.QUICK_PICKUP_PREFERENCES:
            candidate = _round_forward(
                local_now + timedelta(minutes=minutes),
                settings.pickup_interval_minutes,
            )
            validation = self.validate(candidate, now=now)
            if not validation.is_valid or validation.requested_at in seen:
                continue
            seen.add(validation.requested_at)
            options.append(
                QuickPickupOption(
                    key=f"preference-{minutes}",
                    label=f"{minutes} min",
                    requested_at=validation.requested_at,
                    preference_minutes=minutes,
                )
            )

        custom_pickup_at = None
        custom_pickup_error = None
        if custom_pickup_time is not None:
            custom_candidate = datetime.combine(
                local_now.date(),
                custom_pickup_time.replace(tzinfo=None),
                tzinfo=timezone,
            )
            custom_validation = self.validate(custom_candidate, now=now)
            if custom_validation.is_valid:
                custom_pickup_at = custom_validation.requested_at
            else:
                custom_pickup_error = custom_validation.message

        return SchedulingOptions(
            server_now=local_now,
            business_timezone=settings.timezone,
            ordering_available=True,
            ordering_status="open",
            ordering_mode=self._ordering_mode(settings),
            shop_open=shop_open,
            status_reason=status_reason,
            unavailable_reason=None,
            minimum_lead_time_minutes=settings.minimum_lead_time_minutes,
            pickup_interval_minutes=settings.pickup_interval_minutes,
            maximum_advance_days=settings.maximum_advance_days,
            earliest_pickup_at=earliest,
            quick_pickup_options=tuple(options),
            custom_pickup_at=custom_pickup_at,
            custom_pickup_error=custom_pickup_error,
        )

    @staticmethod
    def _options_unavailable(
        local_now: datetime,
        settings: BusinessSettings,
        reason: str,
        *,
        ordering_status: str,
        shop_open: bool,
        earliest_pickup_at: datetime | None = None,
    ) -> SchedulingOptions:
        return SchedulingOptions(
            server_now=local_now,
            business_timezone=settings.timezone,
            ordering_available=False,
            ordering_status=ordering_status,
            ordering_mode=PickupSchedulingService._ordering_mode(settings),
            shop_open=shop_open,
            status_reason=reason,
            unavailable_reason=reason,
            minimum_lead_time_minutes=settings.minimum_lead_time_minutes,
            pickup_interval_minutes=settings.pickup_interval_minutes,
            maximum_advance_days=settings.maximum_advance_days,
            earliest_pickup_at=earliest_pickup_at,
            quick_pickup_options=(),
        )

    @staticmethod
    def _ordering_mode(settings: BusinessSettings) -> str:
        if not settings.ordering_enabled:
            return "force_closed"
        return settings.ordering_mode or "schedule"

    def _current_state(
        self,
        settings: BusinessSettings,
        local_now: datetime,
    ) -> tuple[bool, bool, str, str | None]:
        closure = self._repository.get_business_closure(local_now.date())
        hours = self._repository.get_business_hour(local_now.weekday())
        shop_open = bool(
            closure is None
            and hours is not None
            and not hours.is_closed
            and self._inside_hours(local_now, hours)
        )
        mode = self._ordering_mode(settings)
        if mode == "force_closed":
            return False, shop_open, "paused", "Paused by owner."
        if mode == "force_open":
            return (
                True,
                shop_open,
                "open",
                "Regular business hours are temporarily overridden.",
            )
        if closure is not None:
            reason = (
                f"Closed for {closure.reason}."
                if closure.reason
                else "Closed for a scheduled closure."
            )
            return False, False, "closed", reason
        if not shop_open:
            return (
                False,
                False,
                "closed",
                "The café is currently outside its business hours.",
            )
        return True, True, "open", None

    def _settings(self) -> BusinessSettings:
        settings = self._repository.get_business_settings()
        if settings is None:
            raise AvailabilityConfigurationError(
                "Business settings have not been configured."
            )
        _business_timezone(settings)
        return settings

    @staticmethod
    def _inside_hours(requested_at: datetime, hours: BusinessHour) -> bool:
        assert hours.opens_at is not None
        assert hours.closes_at is not None
        requested_time = requested_at.timetz().replace(tzinfo=None)
        return hours.opens_at <= requested_time < hours.closes_at

    @staticmethod
    def _next_day(value: datetime) -> datetime:
        return (value + timedelta(days=1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    @staticmethod
    def _invalid(
        code: PickupValidationCode,
        requested_at: datetime,
        message: str,
    ) -> PickupValidation:
        return PickupValidation(
            is_valid=False,
            code=code,
            requested_at=requested_at,
            message=message,
        )


class SellabilityService:
    def __init__(self, repository: AvailabilityRepositoryProtocol) -> None:
        self._repository = repository

    def evaluate(
        self,
        product_id: int,
        *,
        at: datetime,
    ) -> Sellability:
        _require_aware(at, "at")
        settings = self._repository.get_business_settings()
        if settings is None:
            raise AvailabilityConfigurationError(
                "Business settings have not been configured."
            )
        business_date = at.astimezone(_business_timezone(settings)).date()
        product = self._repository.get_product(product_id)

        if product is None:
            return Sellability(False, product_id, business_date, "Product not found.")
        if not product.category.is_published:
            return Sellability(
                False,
                product_id,
                business_date,
                "Product category is not published.",
            )
        if not product.is_published or product.archived_at is not None:
            return Sellability(
                False,
                product_id,
                business_date,
                "Product is not published.",
            )

        default = self._repository.get_product_availability(product_id)
        override = self._repository.get_product_availability_override(
            product_id,
            business_date,
        )
        if override is not None:
            return Sellability(
                override.is_available,
                product_id,
                business_date,
                None
                if override.is_available
                else override.reason or "Product is sold out.",
            )
        if default is not None and not default.default_available:
            return Sellability(
                False,
                product_id,
                business_date,
                default.reason or "Product is sold out.",
            )

        return Sellability(True, product_id, business_date)
