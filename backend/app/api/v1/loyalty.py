from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.customer_auth import current_customer
from app.api.v1.orders import get_order_session
from app.api.v1.owner_auth import require_permission, require_read_permission
from app.jds_auth.service import AuthPrincipal
from app.loyalty.models import LoyaltyProgramProduct
from app.loyalty.service import DEFAULTS, LoyaltyService

router = APIRouter(tags=["loyalty"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProgramInput(Strict):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    enabled: bool
    stamps_required: int = Field(ge=1, le=100)
    reward_description: str = Field(min_length=1, max_length=200)
    earning_product_ids: list[int] = Field(max_length=1000)
    reward_product_ids: list[int] = Field(max_length=1000)

    @model_validator(mode="after")
    def valid(self):
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.reward_description = self.reward_description.strip()
        if not self.name or not self.description or not self.reward_description:
            raise ValueError("Program text must not be blank.")
        if len(set(self.earning_product_ids)) != len(self.earning_product_ids) or len(set(self.reward_product_ids)) != len(self.reward_product_ids):
            raise ValueError("Product selections must be unique.")
        if self.enabled and (not self.earning_product_ids or not self.reward_product_ids):
            raise ValueError("Enabled programs require earning and reward products.")
        return self


class AdjustmentInput(Strict):
    customer_user_id: UUID
    program_id: UUID
    quantity: int = Field(ge=-100, le=100)
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def nonzero(self):
        if self.quantity == 0:
            raise ValueError("Adjustment must not be zero.")
        self.reason = self.reason.strip()
        return self


def program_json(service: LoyaltyService, program) -> dict:
    products = list(service.session.scalars(select(LoyaltyProgramProduct).where(LoyaltyProgramProduct.loyalty_program_id == program.id)))
    return {"id": str(program.id), "name": program.name, "description": program.description, "enabled": program.enabled, "stamps_required": program.stamps_required, "reward_description": program.reward_description, "earning_rule": program.earning_rule, "earning_product_ids": [p.product_id for p in products if p.earning_eligible and p.product_id is not None], "reward_product_ids": [p.product_id for p in products if p.reward_eligible and p.product_id is not None]}


def summary_json(item: dict, *, include_activity: bool = True) -> dict:
    program, balance = item["program"], item["balance"]
    payload = {"id": str(program.id), "name": program.name, "description": program.description, "enabled": program.enabled, "stamps_required": program.stamps_required, "stamps": balance.stamps, "remaining": max(0, program.stamps_required - balance.stamps), "rewards_available": balance.rewards_available, "reward_description": program.reward_description}
    if include_activity:
        labels = {"stamp_earned": "Stamp earned from completed order", "reward_earned": "Free drink reward earned", "reward_redeemed": "Free drink reward used", "manual_adjustment": "Owner adjustment", "reversal": "Correction"}
        payload["activity"] = [{"type": e.event_type, "label": labels[e.event_type], "quantity": e.quantity, "created_at": e.created_at} for e in item["activity"]]
    return payload


@router.get("/customer/loyalty")
def customer_loyalty(response: Response, principal: AuthPrincipal = Depends(current_customer), session: Session = Depends(get_order_session)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return {"programs": [summary_json(item) for item in LoyaltyService(session).customer_summary(principal.user_id, principal.organization_id, include_inactive=True)]}


@router.get("/owner/loyalty")
def owner_loyalty(response: Response, principal: AuthPrincipal = Depends(require_read_permission("loyalty.manage")), session: Session = Depends(get_order_session)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    service = LoyaltyService(session)
    programs = service.programs(principal.organization_id)
    return {"programs": [program_json(service, p) for p in programs], "default_program": DEFAULTS, "products": service.catalog(principal.organization_id)}


@router.put("/owner/loyalty/program")
def save_program(payload: ProgramInput, principal: AuthPrincipal = Depends(require_permission("loyalty.manage")), session: Session = Depends(get_order_session)) -> dict:
    service = LoyaltyService(session)
    try:
        program = service.save_program(principal.organization_id, program_id=payload.id, values=payload.model_dump(), earning_product_ids=set(payload.earning_product_ids), reward_product_ids=set(payload.reward_product_ids))
    except ValueError as error:
        messages = {"threshold_has_history": "The stamp target cannot change after customers have loyalty history. Existing progress and earned rewards were preserved."}
        raise HTTPException(404 if str(error) in ("program_not_found", "product_not_found") else 409, detail={"code": str(error), "message": messages.get(str(error), "Loyalty configuration could not be saved.")}) from error
    return program_json(service, program)


@router.get("/owner/loyalty/customers")
def search_customers(q: str = Query(min_length=2, max_length=100), principal: AuthPrincipal = Depends(require_read_permission("loyalty.adjust")), session: Session = Depends(get_order_session)) -> dict:
    service = LoyaltyService(session)
    return {"customers": [{"id": str(user.id), "name": user.display_name, "email": user.primary_email, "programs": [summary_json(item, include_activity=False) for item in service.customer_summary(user.id, principal.organization_id, include_inactive=True)]} for user in service.customers(principal.organization_id, q)]}


@router.post("/owner/loyalty/adjustments", status_code=201)
def adjust(payload: AdjustmentInput, principal: AuthPrincipal = Depends(require_permission("loyalty.adjust")), session: Session = Depends(get_order_session)) -> dict:
    service = LoyaltyService(session)
    program = service.program(principal.organization_id, payload.program_id)
    if program is None or service.customer(principal.organization_id, payload.customer_user_id) is None:
        raise HTTPException(404, detail={"code": "loyalty_target_not_found", "message": "Customer or loyalty program was not found."})
    try:
        event = service.adjust(payload.customer_user_id, program, quantity=payload.quantity, actor_user_id=principal.user_id, reason=payload.reason)
    except ValueError as error:
        raise HTTPException(409, detail={"code": str(error), "message": "That loyalty adjustment is not valid."}) from error
    balance = service.balance(payload.customer_user_id, program)
    return {"event_at": event.created_at, "stamps": balance.stamps, "rewards_available": balance.rewards_available}
