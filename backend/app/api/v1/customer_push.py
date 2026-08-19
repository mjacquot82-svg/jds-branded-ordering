from datetime import datetime, timezone
import base64
from urllib.parse import urlparse
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.v1.customer_auth import current_customer, customer_csrf
from app.api.v1.orders import get_order_session
from app.jds_auth.service import AuthPrincipal
from app.jds_auth.service import utc_now
from app.jds_auth.rate_limit import DatabaseAuthRateLimiter, PUSH_SUBSCRIBE_ACCOUNT, RateLimitExceeded
from app.push.config import PushSettings
from app.push.models import CustomerNotificationPreference, WebPushSubscription
from app.push.security import SubscriptionProtector, endpoint_fingerprint

router = APIRouter(prefix="/customer/push", tags=["customer-push"])
class Strict(BaseModel): model_config = ConfigDict(extra="forbid")

def validate_base64url(value: str, expected_length: int) -> str:
    try:
        raw = base64.b64decode(
            value + "=" * ((4-len(value)%4)%4), altchars=b"-_", validate=True
        )
    except Exception as exc:
        raise ValueError("Invalid subscription key") from exc
    if len(raw) != expected_length:
        raise ValueError("Invalid subscription key length")
    return value

def validate_endpoint(value: str) -> str:
    parsed=urlparse(value)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Push endpoint must be a valid HTTPS URL")
    return value

class Keys(Strict):
    p256dh: str = Field(min_length=40, max_length=200)
    auth: str = Field(min_length=8, max_length=100)
    @field_validator("p256dh")
    @classmethod
    def valid_p256dh(cls, value: str) -> str: return validate_base64url(value, 65)
    @field_validator("auth")
    @classmethod
    def valid_auth(cls, value: str) -> str: return validate_base64url(value, 16)
class SubscriptionInput(Strict):
    endpoint: str = Field(min_length=20, max_length=2048)
    keys: Keys
    content_encoding: str = Field(default="aes128gcm", pattern="^aes128gcm$")
    device_label: str | None = Field(default=None, max_length=120)
    @field_validator("endpoint")
    @classmethod
    def valid_endpoint(cls, value: str) -> str: return validate_endpoint(value)
class PreferenceInput(Strict): lunch_special_enabled: bool
class EndpointInput(Strict):
    endpoint: str = Field(min_length=20, max_length=2048)
    @field_validator("endpoint")
    @classmethod
    def valid_endpoint(cls, value: str) -> str: return validate_endpoint(value)

def settings(request: Request) -> PushSettings: return request.app.state.push_settings
def protector(config: PushSettings) -> SubscriptionProtector:
    if not config.encryption_key: raise HTTPException(503, detail={"code":"push_unavailable","message":"Notifications are not configured."})
    try: return SubscriptionProtector(config.encryption_key)
    except Exception as exc: raise HTTPException(503, detail={"code":"push_unavailable","message":"Notifications are not configured."}) from exc

@router.get("/config")
def config(response: Response, _: AuthPrincipal = Depends(current_customer), config: PushSettings = Depends(settings)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return {"release_enabled": config.active, "enrollment_enabled": config.can_enroll, "vapid_public_key": config.vapid_public_key if config.can_enroll else None}

@router.get("/status")
def status(response: Response, principal: AuthPrincipal = Depends(current_customer), session: Session = Depends(get_order_session)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    pref = session.scalar(select(CustomerNotificationPreference).where(CustomerNotificationPreference.customer_user_id==principal.user_id, CustomerNotificationPreference.notification_kind=="lunch_special"))
    subscriptions = session.scalars(select(WebPushSubscription).where(WebPushSubscription.customer_user_id==principal.user_id, WebPushSubscription.revoked_at.is_(None), WebPushSubscription.expired_at.is_(None))).all()
    return {"lunch_special_enabled": bool(pref and pref.enabled), "active_device_count": len(subscriptions), "subscriptions": [{"id":str(s.id),"device_label":s.device_label,"last_confirmed_at":s.last_confirmed_at} for s in subscriptions]}

@router.post("/subscriptions", status_code=201)
def subscribe(payload: SubscriptionInput, request:Request, principal: AuthPrincipal=Depends(customer_csrf), now:datetime=Depends(utc_now), session: Session=Depends(get_order_session), config: PushSettings=Depends(settings)) -> dict:
    auth_settings=request.app.state.auth_settings
    if auth_settings is not None:
        try: DatabaseAuthRateLimiter(session,auth_settings.session_pepper).check(PUSH_SUBSCRIBE_ACCOUNT,str(principal.user_id),now=now)
        except RateLimitExceeded as error: raise HTTPException(429,detail={"code":"rate_limited","message":"Too many notification setup requests. Try again later."},headers={"Retry-After":str(error.retry_after)}) from error
    if not config.can_enroll: raise HTTPException(503, detail={"code":"push_enrollment_disabled","message":"Notification enrollment is not available yet."})
    now=datetime.now(timezone.utc); fp=endpoint_fingerprint(payload.endpoint); crypt=protector(config)
    item=session.scalar(select(WebPushSubscription).where(WebPushSubscription.endpoint_fingerprint==fp))
    if item and item.customer_user_id != principal.user_id: raise HTTPException(409, detail={"code":"subscription_in_use","message":"This browser subscription is already registered."})
    if not item:
        item=WebPushSubscription(customer_user_id=principal.user_id, endpoint_fingerprint=fp, endpoint_ciphertext=b"",p256dh_ciphertext=b"",auth_ciphertext=b"")
        session.add(item)
    item.endpoint_ciphertext=crypt.encrypt(payload.endpoint); item.p256dh_ciphertext=crypt.encrypt(payload.keys.p256dh); item.auth_ciphertext=crypt.encrypt(payload.keys.auth)
    item.content_encoding=payload.content_encoding; item.device_label=payload.device_label; item.last_confirmed_at=now; item.revoked_at=None; item.expired_at=None
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        item=session.scalar(select(WebPushSubscription).where(WebPushSubscription.endpoint_fingerprint==fp))
        if item is None or item.customer_user_id != principal.user_id:
            raise HTTPException(409, detail={"code":"subscription_in_use","message":"This browser subscription is already registered."})
    return {"id":str(item.id)}

@router.post("/subscriptions/revoke-current", status_code=204)
def revoke_current(payload: EndpointInput, principal: AuthPrincipal=Depends(customer_csrf), session: Session=Depends(get_order_session)) -> Response:
    item=session.scalar(select(WebPushSubscription).where(WebPushSubscription.endpoint_fingerprint==endpoint_fingerprint(payload.endpoint)))
    if item and item.customer_user_id == principal.user_id and item.revoked_at is None:
        item.revoked_at=datetime.now(timezone.utc); session.commit()
    return Response(status_code=204)

@router.delete("/subscriptions/{subscription_id}", status_code=204)
def unsubscribe(subscription_id: UUID, principal: AuthPrincipal=Depends(customer_csrf), session: Session=Depends(get_order_session)) -> Response:
    item=session.get(WebPushSubscription, subscription_id)
    if item and item.customer_user_id==principal.user_id and item.revoked_at is None:
        item.revoked_at=datetime.now(timezone.utc); session.commit()
    return Response(status_code=204)

@router.put("/preferences")
def preference(payload: PreferenceInput, principal: AuthPrincipal=Depends(customer_csrf), session: Session=Depends(get_order_session), config: PushSettings=Depends(settings)) -> dict:
    if payload.lunch_special_enabled:
        active_subscription=session.scalar(select(WebPushSubscription.id).where(WebPushSubscription.customer_user_id==principal.user_id,WebPushSubscription.revoked_at.is_(None),WebPushSubscription.expired_at.is_(None)).limit(1))
        if not config.can_enroll or active_subscription is None:
            raise HTTPException(409, detail={"code":"subscription_required","message":"Enable notifications on a device first."})
    now=datetime.now(timezone.utc); item=session.scalar(select(CustomerNotificationPreference).where(CustomerNotificationPreference.customer_user_id==principal.user_id, CustomerNotificationPreference.notification_kind=="lunch_special"))
    if not item: item=CustomerNotificationPreference(customer_user_id=principal.user_id,notification_kind="lunch_special"); session.add(item)
    item.enabled=payload.lunch_special_enabled; item.enabled_at=now if payload.lunch_special_enabled else item.enabled_at; item.disabled_at=None if payload.lunch_special_enabled else now
    session.commit(); return {"lunch_special_enabled":item.enabled}
