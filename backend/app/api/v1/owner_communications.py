from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.orders import get_order_session
from app.api.v1.owner_auth import require_read_permission, require_permission
from app.jds_auth.rate_limit import DatabaseAuthRateLimiter, PUSH_ANNOUNCE_ACTOR, RateLimitExceeded
from app.jds_auth.service import utc_now
from app.push.trigger import drain_push_outbox
from app.communications.service import CommunicationCenterService
from app.jds_auth.service import AuthPrincipal

router = APIRouter(prefix="/owner/communications", tags=["owner-communications"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Summary(StrictModel):
    actionable_warnings: int
    lunch_special_attempting_today: bool
    lunch_special_queued_today: bool
    push_release_enabled: bool


class LunchSpecial(StrictModel):
    id: str
    name: str
    description: str
    price_cents: int
    image: str
    customer_visible: bool
    orderable: bool
    warnings: list[str]


class Activity(StrictModel):
    id: str
    kind: str
    title: str
    message: str
    status: str
    occurred_at: datetime
    sent_by: str
    queued: int = 0
    attempted: int = 0
    accepted: int = 0
    failed: int = 0
    expired: int = 0
    suppressed: int = 0
    clicked: int = 0

class LunchSend(StrictModel):
    kind: str
    override: bool = False
    confirm_override: bool = False
class GeneralSend(StrictModel):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=280)
    target_route: str = Field(default="/", max_length=300)


class Health(StrictModel):
    key: str
    name: str
    status: str
    detail: str
    actionable: bool


class CommunicationCenterResponse(StrictModel):
    generated_at: datetime
    summary: Summary
    lunch_special: LunchSpecial | None
    activity: list[Activity]
    health: list[Health]


@router.get("", response_model=CommunicationCenterResponse)
def communication_center(
    request: Request,
    background_tasks: BackgroundTasks,
    principal: AuthPrincipal = Depends(require_read_permission("communications.announce")),
    session: Session = Depends(get_order_session),
) -> CommunicationCenterResponse:
    try:
        result = CommunicationCenterResponse.model_validate(
            CommunicationCenterService(session, request.app.state.push_settings).snapshot(
                organization_id=principal.organization_id
            )
        )
        background_tasks.add_task(
            drain_push_outbox,
            request.app.state.db_session_factory,
            request.app.state.push_settings,
        )
        return result
    except (SQLAlchemyError, ValueError) as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "communications_unavailable",
                "message": "Communication status is temporarily unavailable.",
            },
        ) from error

def key(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized or len(normalized) > 100 or not all(character.isalnum() or character in "-_" for character in normalized):
        raise HTTPException(400, detail={"code":"idempotency_required","message":"A valid Idempotency-Key is required."})
    return normalized

def response(item) -> dict: return {"id":str(item.id),"status":item.status}

def enforce_push_limit(request: Request, session: Session, principal: AuthPrincipal, now: datetime) -> None:
    settings = request.app.state.auth_settings
    if settings is None:  # Dependency-overridden tests have no live authentication service.
        return
    try:
        DatabaseAuthRateLimiter(session, settings.session_pepper).check(PUSH_ANNOUNCE_ACTOR, str(principal.user_id), now=now)
    except RateLimitExceeded as error:
        raise HTTPException(429, detail={"code":"rate_limited","message":"Too many announcement requests. Try again later."}, headers={"Retry-After":str(error.retry_after)}) from error

@router.post("/lunch-special", status_code=202)
def send_lunch(payload: LunchSend, request: Request, background_tasks: BackgroundTasks, idempotency_key: str|None=Header(None,alias="Idempotency-Key"), principal:AuthPrincipal=Depends(require_permission("communications.announce")), now:datetime=Depends(utc_now), session:Session=Depends(get_order_session)) -> dict:
    enforce_push_limit(request,session,principal,now)
    if payload.kind != "lunch_special": raise HTTPException(422, detail={"code":"kind_invalid","message":"Lunch Special intent is required."})
    if payload.override and (principal.role != "owner" or not payload.confirm_override): raise HTTPException(403, detail={"code":"override_forbidden","message":"Only an Owner may explicitly confirm a resend."})
    try:
        item = CommunicationCenterService(session,request.app.state.push_settings).create_lunch_special(organization_id=principal.organization_id,actor_user_id=principal.user_id,actor_name=principal.display_name,idempotency_key=key(idempotency_key),override=payload.override)
        background_tasks.add_task(drain_push_outbox, request.app.state.db_session_factory, request.app.state.push_settings)
        return response(item)
    except ValueError as error:
        codes={"duplicate_lunch_special":(409,"Today’s Lunch Special was already queued."),"idempotency_conflict":(409,"This request key was already used for a different announcement."),"push_not_released":(503,"Push notifications are not release-enabled."),"lunch_special_missing":(409,"Select a Lunch Special first."),"lunch_special_not_orderable":(409,"The current Lunch Special is not orderable.")}
        status,message=codes.get(str(error),(409,"Announcement could not be queued.")); raise HTTPException(status,detail={"code":str(error),"message":message}) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(503,detail={"code":"communications_unavailable","message":"The announcement could not be queued."}) from error

@router.post("/general", status_code=202)
def send_general(payload:GeneralSend, request:Request,background_tasks:BackgroundTasks,idempotency_key:str|None=Header(None,alias="Idempotency-Key"),principal:AuthPrincipal=Depends(require_permission("communications.general_announce")),now:datetime=Depends(utc_now),session:Session=Depends(get_order_session)) -> dict:
    enforce_push_limit(request,session,principal,now)
    title=payload.title.strip(); body=payload.body.strip(); route=payload.target_route
    if not (1<=len(title)<=80 and 1<=len(body)<=280): raise HTTPException(422,detail={"code":"content_invalid","message":"Title and message are required and too long."})
    if not route.startswith("/") or route.startswith("//") or ":" in route or route.split("?",1)[0] not in {"/","/menu","/account","/orders"}: raise HTTPException(422,detail={"code":"route_invalid","message":"Choose an approved Ladel’s destination."})
    try:
        item = CommunicationCenterService(session,request.app.state.push_settings).create_general(organization_id=principal.organization_id,actor_user_id=principal.user_id,actor_name=principal.display_name,idempotency_key=key(idempotency_key),title=title,body=body,route=route)
        background_tasks.add_task(drain_push_outbox, request.app.state.db_session_factory, request.app.state.push_settings)
        return response(item)
    except ValueError as error:
        status=409 if str(error)=="idempotency_conflict" else 503
        message="This request key was already used for a different announcement." if status==409 else "Push notifications are not release-enabled."
        raise HTTPException(status,detail={"code":str(error),"message":message}) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(503,detail={"code":"communications_unavailable","message":"The announcement could not be queued."}) from error
