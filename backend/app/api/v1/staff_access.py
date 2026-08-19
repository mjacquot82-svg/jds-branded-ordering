from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.owner_auth import (
    client_identifier, enforce_limit, get_auth_service, get_auth_settings,
    require_permission, require_read_permission, require_trusted_origin, session_response,
)
from app.db.session import get_db_session
from app.jds_auth.audit import DatabaseSecurityAuditWriter
from app.jds_auth.config import AuthSettings
from app.jds_auth.models import JdsApplication, JdsUser, Membership, Organization, Role, StaffPinCredential
from app.jds_auth.provider import ProviderAuthentication, ProviderIdentity
from app.jds_auth.rate_limit import STAFF_LOGIN_ACCOUNT, STAFF_LOGIN_IP
from app.jds_auth.repository import AuthRepository
from app.jds_auth.schemas import (
    MessageResponse, SessionResponse, StaffAccessOption, StaffAccountResponse,
    StaffCreateRequest, StaffPinLoginRequest, StaffPinResetRequest,
    StaffStatusRequest,
)
from app.jds_auth.security import hash_pin, pin_matches
from app.jds_auth.service import AuthPrincipal, AuthenticationService, utc_now

router = APIRouter(tags=["staff-access"])


def _account_response(user: JdsUser, credential: StaffPinCredential) -> StaffAccountResponse:
    return StaffAccountResponse(
        id=user.id, display_name=user.display_name, active=user.status == "active",
        created_at=user.created_at, pin_changed_at=credential.changed_at,
    )


def _staff_rows(session: Session, settings: AuthSettings, *, active_only: bool = False, application_id: UUID | None = None, organization_id: UUID | None = None):
    query = (
        select(JdsUser, Membership, StaffPinCredential)
        .join(Membership, Membership.user_id == JdsUser.id)
        .join(Role, Role.id == Membership.role_id)
        .join(StaffPinCredential, StaffPinCredential.membership_id == Membership.id)
        .where(Role.key == "staff", Membership.status == "active")
        .order_by(JdsUser.display_name, JdsUser.id)
    )
    if application_id is None or organization_id is None:
        query = query.join(JdsApplication, JdsApplication.id == Membership.application_id).join(Organization, Organization.id == Membership.organization_id).where(JdsApplication.key == settings.application_key, Organization.slug == settings.organization_slug)
    else:
        query = query.where(Membership.application_id == application_id, Membership.organization_id == organization_id)
    if active_only:
        query = query.where(JdsUser.status == "active")
    return session.execute(query).all()


@router.get("/staff/access/accounts", response_model=list[StaffAccessOption])
def access_options(
    session: Session = Depends(get_db_session),
    settings: AuthSettings = Depends(get_auth_settings),
) -> list[StaffAccessOption]:
    return [StaffAccessOption(id=user.id, display_name=user.display_name) for user, _, _ in _staff_rows(session, settings, active_only=True)]


@router.post("/staff/access/login", response_model=SessionResponse)
def staff_login(
    payload: StaffPinLoginRequest, response: Response, request: Request,
    _: None = Depends(require_trusted_origin),
    service: AuthenticationService = Depends(get_auth_service),
    settings: AuthSettings = Depends(get_auth_settings),
    now: datetime = Depends(utc_now),
) -> SessionResponse:
    enforce_limit(service, STAFF_LOGIN_IP, client_identifier(request), now)
    enforce_limit(service, STAFF_LOGIN_ACCOUNT, str(payload.staff_id), now)
    try:
        with service._session.begin():
            row = service._session.execute(
                select(JdsUser, Membership, Role, StaffPinCredential)
                .join(Membership, Membership.user_id == JdsUser.id)
                .join(Role, Role.id == Membership.role_id)
                .join(StaffPinCredential, StaffPinCredential.membership_id == Membership.id)
                .join(JdsApplication, JdsApplication.id == Membership.application_id)
                .join(Organization, Organization.id == Membership.organization_id)
                .where(
                    JdsUser.id == payload.staff_id,
                    JdsApplication.key == settings.application_key,
                    Organization.slug == settings.organization_slug,
                    Organization.is_active.is_(True),
                )
                .with_for_update()
            ).first()
            if (
                row is None or row.Role.key != "staff" or row.JdsUser.status != "active"
                or row.JdsUser.credential_state != "active" or row.Membership.status != "active"
                or not pin_matches(payload.pin, row.StaffPinCredential.verifier, settings.session_pepper)
            ):
                raise ValueError("invalid staff credential")
            authentication = ProviderAuthentication(
                ProviderIdentity("jds-local-pin", str(row.JdsUser.id), row.JdsUser.primary_email, True, "aal1"), ""
            )
            row.JdsUser.last_authenticated_at = now
            issued = service._issue(row.JdsUser, row.Membership, authentication, now, request.headers.get("user-agent"), False)
            DatabaseSecurityAuditWriter(service._session).record(
                "auth.staff_pin_login", "success", organization_id=row.Membership.organization_id,
                actor_user_id=row.JdsUser.id, session_id=issued.principal.session_id,
            )
    except (ValueError, SQLAlchemyError):
        raise HTTPException(status_code=401, detail={"code": "authentication_failed", "message": "Staff member or PIN is invalid."})
    response.set_cookie(settings.session_cookie_name, issued.token, max_age=settings.session_absolute_hours * 3600, secure=settings.secure_cookies, httponly=True, samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return session_response(issued.principal, issued.csrf_token)


@router.get("/owner/staff", response_model=list[StaffAccountResponse])
def list_staff(
    principal: AuthPrincipal = Depends(require_read_permission("members.manage")),
    session: Session = Depends(get_db_session), settings: AuthSettings = Depends(get_auth_settings),
) -> list[StaffAccountResponse]:
    return [_account_response(user, credential) for user, _, credential in _staff_rows(session, settings, application_id=principal.application_id, organization_id=principal.organization_id)]


@router.post("/owner/staff", response_model=StaffAccountResponse, status_code=201)
def create_staff(
    payload: StaffCreateRequest,
    principal: AuthPrincipal = Depends(require_permission("members.manage")),
    session: Session = Depends(get_db_session), settings: AuthSettings = Depends(get_auth_settings),
    now: datetime = Depends(utc_now),
) -> StaffAccountResponse:
    with session.begin():
        role = session.scalar(select(Role).where(Role.application_id == principal.application_id, Role.key == "staff"))
        if role is None:
            raise HTTPException(status_code=503, detail="Staff authorization is unavailable.")
        user_id = uuid4()
        user = JdsUser(id=user_id, primary_email=f"{user_id}@staff.invalid", display_name=payload.display_name, status="active", email_verified_at=now)
        membership = Membership(organization_id=principal.organization_id, application_id=principal.application_id, user_id=user_id, role_id=role.id, status="active", joined_at=now)
        session.add_all([user, membership])
        session.flush()
        credential = StaffPinCredential(membership_id=membership.id, user_id=user_id, verifier=hash_pin(payload.pin, settings.session_pepper), changed_at=now)
        session.add(credential)
        DatabaseSecurityAuditWriter(session).record("staff.access_created", "success", organization_id=principal.organization_id, actor_user_id=principal.user_id, session_id=principal.session_id, target_type="user", target_id=str(user_id))
    return _account_response(user, credential)


def _managed_staff(session: Session, principal: AuthPrincipal, staff_id: UUID):
    row = session.execute(
        select(JdsUser, Membership, Role, StaffPinCredential)
        .join(Membership, Membership.user_id == JdsUser.id)
        .join(Role, Role.id == Membership.role_id)
        .join(StaffPinCredential, StaffPinCredential.membership_id == Membership.id)
        .where(JdsUser.id == staff_id, Membership.organization_id == principal.organization_id, Membership.application_id == principal.application_id, Role.key == "staff")
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Staff access account was not found.")
    return row


@router.put("/owner/staff/{staff_id}/pin", response_model=MessageResponse)
def reset_staff_pin(payload: StaffPinResetRequest, staff_id: UUID, principal: AuthPrincipal = Depends(require_permission("members.manage")), session: Session = Depends(get_db_session), settings: AuthSettings = Depends(get_auth_settings), now: datetime = Depends(utc_now)) -> MessageResponse:
    with session.begin():
        row = _managed_staff(session, principal, staff_id)
        row.StaffPinCredential.verifier = hash_pin(payload.pin, settings.session_pepper)
        row.StaffPinCredential.changed_at = now
        row.JdsUser.security_version += 1
        AuthRepository(session).revoke_user_sessions(staff_id, now, "staff_pin_reset")
        DatabaseSecurityAuditWriter(session).record("staff.pin_reset", "success", organization_id=principal.organization_id, actor_user_id=principal.user_id, session_id=principal.session_id, target_type="user", target_id=str(staff_id))
    return MessageResponse(message="PIN updated. Existing Staff sessions were signed out.")


@router.put("/owner/staff/{staff_id}/status", response_model=StaffAccountResponse)
def set_staff_status(payload: StaffStatusRequest, staff_id: UUID, principal: AuthPrincipal = Depends(require_permission("members.manage")), session: Session = Depends(get_db_session), settings: AuthSettings = Depends(get_auth_settings), now: datetime = Depends(utc_now)) -> StaffAccountResponse:
    with session.begin():
        row = _managed_staff(session, principal, staff_id)
        row.JdsUser.status = "active" if payload.active else "disabled"
        row.JdsUser.security_version += 1
        AuthRepository(session).revoke_user_sessions(staff_id, now, "staff_access_status_changed")
        DatabaseSecurityAuditWriter(session).record("staff.access_enabled" if payload.active else "staff.access_disabled", "success", organization_id=principal.organization_id, actor_user_id=principal.user_id, session_id=principal.session_id, target_type="user", target_id=str(staff_id))
    return _account_response(row.JdsUser, row.StaffPinCredential)
