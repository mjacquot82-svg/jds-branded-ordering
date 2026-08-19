from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.orders import get_current_time, get_order_session
from app.api.v1.owner_auth import require_permission, require_read_permission
from app.api.v1.scheduling import SchedulingOptionsResponse
from app.availability.models import BusinessClosure, BusinessHour
from app.availability.repository import AvailabilityRepository
from app.availability.service import AvailabilityConfigurationError, PickupSchedulingService
from app.jds_auth.service import AuthPrincipal

router = APIRouter(prefix="/owner/scheduling", tags=["owner-scheduling"])


class OwnerSchedulingSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BusinessHourWrite(OwnerSchedulingSchema):
    weekday: int = Field(ge=0, le=6)
    is_closed: bool
    opens_at: time | None = None
    closes_at: time | None = None

    @model_validator(mode="after")
    def validate_period(self) -> "BusinessHourWrite":
        if self.is_closed:
            return self
        if self.opens_at is None or self.closes_at is None:
            raise ValueError("Open days require opening and closing times.")
        if self.opens_at >= self.closes_at:
            raise ValueError("Closing time must be after opening time.")
        return self


class BusinessHoursWrite(OwnerSchedulingSchema):
    hours: list[BusinessHourWrite] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def validate_week(self) -> "BusinessHoursWrite":
        if {entry.weekday for entry in self.hours} != set(range(7)):
            raise ValueError("Business hours must include each day exactly once.")
        return self


class OrderingModeWrite(OwnerSchedulingSchema):
    ordering_mode: Literal["schedule", "force_open", "force_closed"]


class SchedulingPreferencesWrite(OwnerSchedulingSchema):
    minimum_lead_time_minutes: int = Field(ge=0, le=1440)
    pickup_interval_minutes: int = Field(ge=1, le=1440)
    maximum_advance_days: int = Field(ge=1, le=365)


class ClosureWrite(OwnerSchedulingSchema):
    business_date: date
    reopens_on: date | None = None
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_closure(self) -> "ClosureWrite":
        if self.reopens_on is not None and self.reopens_on <= self.business_date:
            raise ValueError("Reopen date must be after the first day closed.")
        if self.reason is not None:
            self.reason = self.reason.strip() or None
        return self


class BusinessHourResponse(OwnerSchedulingSchema):
    weekday: int
    is_closed: bool
    opens_at: time | None
    closes_at: time | None


class ClosureResponse(OwnerSchedulingSchema):
    id: int
    business_date: date
    reopens_on: date | None
    reason: str | None


class OwnerSchedulingResponse(OwnerSchedulingSchema):
    ordering_mode: str
    timezone: str
    minimum_lead_time_minutes: int
    pickup_interval_minutes: int
    maximum_advance_days: int
    hours: list[BusinessHourResponse]
    closures: list[ClosureResponse]
    preview: SchedulingOptionsResponse


def scheduling_error(error: Exception) -> None:
    if isinstance(error, (ValueError, LookupError)):
        raise HTTPException(status_code=409, detail=str(error)) from error
    raise HTTPException(
        status_code=503,
        detail={"code": "scheduling_unavailable", "message": "Scheduling is currently unavailable."},
    ) from error


def build_response(session: Session, now: datetime) -> OwnerSchedulingResponse:
    repository = AvailabilityRepository(session)
    settings = repository.get_business_settings()
    if settings is None:
        raise AvailabilityConfigurationError("Business settings have not been configured.")
    return OwnerSchedulingResponse(
        ordering_mode=PickupSchedulingService._ordering_mode(settings),
        timezone=settings.timezone,
        minimum_lead_time_minutes=settings.minimum_lead_time_minutes,
        pickup_interval_minutes=settings.pickup_interval_minutes,
        maximum_advance_days=settings.maximum_advance_days,
        hours=[
            BusinessHourResponse(
                weekday=entry.weekday,
                is_closed=entry.is_closed,
                opens_at=entry.opens_at,
                closes_at=entry.closes_at,
            )
            for entry in repository.list_business_hours()
        ],
        closures=[
            ClosureResponse(
                id=entry.id,
                business_date=entry.business_date,
                reopens_on=entry.reopens_on,
                reason=entry.reason,
            )
            for entry in repository.list_business_closures()
        ],
        preview=SchedulingOptionsResponse.from_domain(
            PickupSchedulingService(repository).options(now=now)
        ),
    )


@router.get("", response_model=OwnerSchedulingResponse)
def read_owner_scheduling(
    _: AuthPrincipal = Depends(require_read_permission("availability.manage")),
    session: Session = Depends(get_order_session),
    now: datetime = Depends(get_current_time),
) -> OwnerSchedulingResponse:
    try:
        return build_response(session, now)
    except (AvailabilityConfigurationError, SQLAlchemyError) as error:
        scheduling_error(error)


@router.get("/preview", response_model=SchedulingOptionsResponse)
def read_owner_preview(
    _: AuthPrincipal = Depends(require_read_permission("availability.manage")),
    session: Session = Depends(get_order_session),
    now: datetime = Depends(get_current_time),
) -> SchedulingOptionsResponse:
    try:
        return SchedulingOptionsResponse.from_domain(
            PickupSchedulingService(AvailabilityRepository(session)).options(now=now)
        )
    except (AvailabilityConfigurationError, SQLAlchemyError) as error:
        scheduling_error(error)


@router.put("/ordering", response_model=OwnerSchedulingResponse)
def update_ordering(
    payload: OrderingModeWrite,
    _: AuthPrincipal = Depends(require_permission("availability.manage")),
    session: Session = Depends(get_order_session),
    now: datetime = Depends(get_current_time),
) -> OwnerSchedulingResponse:
    try:
        settings = AvailabilityRepository(session).get_business_settings()
        if settings is None:
            raise LookupError("Business settings were not found.")
        settings.ordering_mode = payload.ordering_mode
        settings.ordering_enabled = payload.ordering_mode != "force_closed"
        session.commit()
        return build_response(session, now)
    except (SQLAlchemyError, ValueError, LookupError) as error:
        session.rollback()
        scheduling_error(error)


@router.put("/hours", response_model=OwnerSchedulingResponse)
def update_hours(
    payload: BusinessHoursWrite,
    _: AuthPrincipal = Depends(require_permission("availability.manage")),
    session: Session = Depends(get_order_session),
    now: datetime = Depends(get_current_time),
) -> OwnerSchedulingResponse:
    try:
        repository = AvailabilityRepository(session)
        existing = {entry.weekday: entry for entry in repository.list_business_hours()}
        for value in payload.hours:
            entry = existing.get(value.weekday)
            if entry is None:
                entry = BusinessHour(weekday=value.weekday)
                repository.add(entry)
            entry.is_closed = value.is_closed
            entry.opens_at = None if value.is_closed else value.opens_at
            entry.closes_at = None if value.is_closed else value.closes_at
        session.commit()
        return build_response(session, now)
    except (SQLAlchemyError, ValueError) as error:
        session.rollback()
        scheduling_error(error)


@router.put("/preferences", response_model=OwnerSchedulingResponse)
def update_preferences(
    payload: SchedulingPreferencesWrite,
    _: AuthPrincipal = Depends(require_permission("availability.manage")),
    session: Session = Depends(get_order_session),
    now: datetime = Depends(get_current_time),
) -> OwnerSchedulingResponse:
    try:
        settings = AvailabilityRepository(session).get_business_settings()
        if settings is None:
            raise LookupError("Business settings were not found.")
        settings.minimum_lead_time_minutes = payload.minimum_lead_time_minutes
        settings.pickup_interval_minutes = payload.pickup_interval_minutes
        settings.maximum_advance_days = payload.maximum_advance_days
        session.commit()
        return build_response(session, now)
    except (SQLAlchemyError, ValueError, LookupError) as error:
        session.rollback()
        scheduling_error(error)


def ranges_overlap(first: ClosureWrite, second: BusinessClosure) -> bool:
    first_end = first.reopens_on or first.business_date + timedelta(days=1)
    second_end = second.reopens_on or second.business_date + timedelta(days=1)
    return first.business_date < second_end and second.business_date < first_end


def save_closure(
    payload: ClosureWrite,
    session: Session,
    *,
    closure_id: int | None = None,
) -> None:
    repository = AvailabilityRepository(session)
    for existing in repository.list_business_closures():
        if existing.id != closure_id and ranges_overlap(payload, existing):
            raise ValueError("This closure overlaps an existing closure.")
    closure = session.get(BusinessClosure, closure_id) if closure_id is not None else None
    if closure_id is not None and closure is None:
        raise LookupError("Closure was not found.")
    if closure is None:
        closure = BusinessClosure(business_settings_id=1, business_date=payload.business_date)
        repository.add(closure)
    closure.business_date = payload.business_date
    closure.reopens_on = payload.reopens_on
    closure.reason = payload.reason


@router.post("/closures", response_model=OwnerSchedulingResponse, status_code=201)
def create_closure(
    payload: ClosureWrite,
    _: AuthPrincipal = Depends(require_permission("availability.manage")),
    session: Session = Depends(get_order_session),
    now: datetime = Depends(get_current_time),
) -> OwnerSchedulingResponse:
    try:
        save_closure(payload, session)
        session.commit()
        return build_response(session, now)
    except (SQLAlchemyError, ValueError, LookupError) as error:
        session.rollback()
        scheduling_error(error)


@router.put("/closures/{closure_id}", response_model=OwnerSchedulingResponse)
def update_closure(
    closure_id: int,
    payload: ClosureWrite,
    _: AuthPrincipal = Depends(require_permission("availability.manage")),
    session: Session = Depends(get_order_session),
    now: datetime = Depends(get_current_time),
) -> OwnerSchedulingResponse:
    try:
        save_closure(payload, session, closure_id=closure_id)
        session.commit()
        return build_response(session, now)
    except (SQLAlchemyError, ValueError, LookupError) as error:
        session.rollback()
        scheduling_error(error)


@router.delete("/closures/{closure_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_closure(
    closure_id: int,
    _: AuthPrincipal = Depends(require_permission("availability.manage")),
    session: Session = Depends(get_order_session),
) -> Response:
    closure = session.get(BusinessClosure, closure_id)
    if closure is None:
        raise HTTPException(status_code=404, detail="Closure was not found.")
    try:
        session.delete(closure)
        session.commit()
        return Response(status_code=204)
    except SQLAlchemyError as error:
        session.rollback()
        scheduling_error(error)
