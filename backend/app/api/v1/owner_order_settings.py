"""Owner: per-shop order settings (pay at pickup + new-order alert email)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.orders import get_order_session
from app.api.v1.owner_auth import require_permission, require_read_permission
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.jds_auth.service import AuthPrincipal
from app.payments.pay_at_pickup import OrderSettingsView, get_order_settings, update_order_settings
from app.tenancy.context import TenantContext

router = APIRouter(prefix="/owner/order-settings", tags=["owner-order-settings"])


class OrderSettingsResponse(BaseModel):
    pay_at_pickup_enabled: bool
    pay_at_pickup_min_completed_orders: int
    pay_at_pickup_max_total_cents: int
    new_order_alert_email: str | None

    @classmethod
    def from_view(cls, view: OrderSettingsView) -> "OrderSettingsResponse":
        return cls(**view.__dict__)


class OrderSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pay_at_pickup_enabled: bool
    pay_at_pickup_min_completed_orders: int = Field(default=1, ge=0, le=100)
    pay_at_pickup_max_total_cents: int = Field(default=2500, ge=100, le=100000)
    new_order_alert_email: str | None = Field(default=None, max_length=320)

    @field_validator("new_order_alert_email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        local, _, domain = value.partition("@")
        if not local or "." not in domain or " " in value:
            raise ValueError("Enter a valid email address.")
        return value


@router.get("", response_model=OrderSettingsResponse)
def read_order_settings(
    _: AuthPrincipal = Depends(require_read_permission("orders.read")),
    session: Session = Depends(get_order_session),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
) -> OrderSettingsResponse:
    try:
        return OrderSettingsResponse.from_view(get_order_settings(session, tenant.organization_id))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail={"code": "order_settings_unavailable"}) from error


@router.put("", response_model=OrderSettingsResponse)
def save_order_settings(
    payload: OrderSettingsUpdate,
    _: AuthPrincipal = Depends(require_permission("availability.manage")),
    session: Session = Depends(get_order_session),
    tenant: TenantContext = Depends(authenticated_owner_tenant),
) -> OrderSettingsResponse:
    try:
        view = update_order_settings(session, tenant.organization_id, **payload.model_dump())
        session.commit()
        return OrderSettingsResponse.from_view(view)
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(status_code=503, detail={"code": "order_settings_unavailable"}) from error
