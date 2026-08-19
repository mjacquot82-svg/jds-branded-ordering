from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.orders import get_current_time, get_order_session
from app.api.v1.catalog import ladels_compatibility_tenant
from app.availability.repository import AvailabilityRepository
from app.availability.service import (
    AvailabilityConfigurationError,
    PickupSchedulingService,
    SchedulingOptions,
)
from app.orders.constants import MAX_ORDER_LINES
from app.tenancy.context import TenantContext

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


class SchedulingSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SchedulingLineRequest(SchedulingSchema):
    product_id: int = Field(gt=0)
    variant_id: int | None = Field(default=None, gt=0)
    quantity: int = Field(ge=1)


class SchedulingOptionsRequest(SchedulingSchema):
    lines: list[SchedulingLineRequest] = Field(min_length=1, max_length=MAX_ORDER_LINES)
    custom_pickup_time: time | None = None


class QuickPickupOptionResponse(SchedulingSchema):
    key: str
    label: str
    requested_pickup_at: datetime
    preference_minutes: int | None


class SchedulingOptionsResponse(SchedulingSchema):
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
    quick_pickup_options: list[QuickPickupOptionResponse]
    custom_pickup_at: datetime | None
    custom_pickup_error: str | None

    @classmethod
    def from_domain(cls, value: SchedulingOptions) -> "SchedulingOptionsResponse":
        return cls(
            server_now=value.server_now,
            business_timezone=value.business_timezone,
            ordering_available=value.ordering_available,
            ordering_status=value.ordering_status,
            ordering_mode=value.ordering_mode,
            shop_open=value.shop_open,
            status_reason=value.status_reason,
            unavailable_reason=value.unavailable_reason,
            minimum_lead_time_minutes=value.minimum_lead_time_minutes,
            pickup_interval_minutes=value.pickup_interval_minutes,
            maximum_advance_days=value.maximum_advance_days,
            earliest_pickup_at=value.earliest_pickup_at,
            quick_pickup_options=[
                QuickPickupOptionResponse(
                    key=option.key,
                    label=option.label,
                    requested_pickup_at=option.requested_at,
                    preference_minutes=option.preference_minutes,
                )
                for option in value.quick_pickup_options
            ],
            custom_pickup_at=value.custom_pickup_at,
            custom_pickup_error=value.custom_pickup_error,
        )


@router.post("/options", response_model=SchedulingOptionsResponse)
def scheduling_options(
    request: SchedulingOptionsRequest,
    session: Session = Depends(get_order_session),
    tenant: TenantContext = Depends(ladels_compatibility_tenant),
    now: datetime = Depends(get_current_time),
) -> SchedulingOptionsResponse:
    # Stable cart identifiers are accepted now so cart-derived preparation rules
    # can be added inside the scheduling engine without changing this contract.
    _ = request.lines
    try:
        options = PickupSchedulingService(AvailabilityRepository(session, tenant)).options(
            now=now,
            custom_pickup_time=request.custom_pickup_time,
        )
        return SchedulingOptionsResponse.from_domain(options)
    except (AvailabilityConfigurationError, SQLAlchemyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "scheduling_unavailable",
                "message": "Pickup scheduling is currently unavailable.",
            },
        ) from error
