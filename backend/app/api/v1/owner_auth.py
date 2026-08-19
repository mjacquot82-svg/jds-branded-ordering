from collections.abc import Generator
from datetime import datetime
from typing import Annotated, Callable
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.jds_auth.config import AuthSettings
from app.jds_auth.provider import IdentityProviderError, InvalidCredentialsError
from app.jds_auth.rate_limit import (
    INVITE_ACCEPT_INVITATION,
    INVITE_ACCEPT_IP,
    INVITE_CREATE_ACTOR,
    INVITE_CREATE_ORGANIZATION,
    LOGIN_ACCOUNT,
    LOGIN_IP,
    RESET_COMPLETE_IP,
    RESET_COMPLETE_TOKEN,
    RESET_REQUEST_ACCOUNT,
    RESET_REQUEST_IP,
    DatabaseAuthRateLimiter,
    RateLimit,
    RateLimitExceeded,
)
from app.jds_auth.schemas import (
    AuthorizedOrganizationResponse, InvitationAcceptRequest,
    InvitationCreateRequest,
    LoginRequest,
    MessageResponse,
    PasswordCompletionRequest,
    PasswordResetRequest,
    SessionResponse,
)
from app.jds_auth.service import (
    AuthPrincipal,
    AuthenticationError,
    AuthenticationService,
    CsrfInvalid,
    EmailVerificationRequired,
    MembershipInactive,
    SessionInvalid,
    utc_now,
)

router = APIRouter(prefix="/owner/auth", tags=["owner-auth"])
_TENANT_HEADERS = ("x-tenant-id", "x-organization-id", "x-tenant-slug", "x-organization-slug")
_TENANT_QUERY = ("tenant_id", "organization_id", "tenant_slug", "organization_slug")


def reject_client_tenant_context(request: Request) -> None:
    if any(key in request.headers for key in _TENANT_HEADERS) or any(
        key in request.query_params for key in _TENANT_QUERY
    ):
        auth_error(403, "tenant_context_invalid", "Client-supplied tenant context is not allowed.")


def auth_error(status_code: int, code: str, message: str) -> None:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


def client_identifier(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def enforce_limit(service: AuthenticationService, policy: RateLimit, identifier: str, now: datetime) -> None:
    try:
        DatabaseAuthRateLimiter(service._session, service._settings.session_pepper).check(
            policy,
            identifier,
            now=now,
        )
    except RateLimitExceeded as error:
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Too many requests. Try again later."},
            headers={"Retry-After": str(error.retry_after)},
        ) from error


def get_auth_settings(request: Request) -> AuthSettings:
    settings = request.app.state.auth_settings
    provider = request.app.state.auth_provider
    if settings is None or provider is None:
        auth_error(503, "authentication_unavailable", "Owner authentication is unavailable.")
    return settings


def get_auth_service(request: Request, session: Session = Depends(get_db_session)) -> AuthenticationService:
    settings = get_auth_settings(request)
    return AuthenticationService(session, request.app.state.auth_provider, settings)


def require_trusted_origin(request: Request, settings: AuthSettings = Depends(get_auth_settings)) -> None:
    origin = request.headers.get("origin")
    if origin != settings.frontend_url.rstrip("/"):
        auth_error(403, "origin_invalid", "Request origin is not allowed.")


def current_principal(
    request: Request,
    service: AuthenticationService = Depends(get_auth_service),
    now: datetime = Depends(utc_now),
) -> AuthPrincipal:
    reject_client_tenant_context(request)
    settings = get_auth_settings(request)
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        auth_error(401, "unauthenticated", "Authentication is required.")
    try:
        principal = service.resolve(token, now=now)
        service._session.commit()
        return principal
    except SessionInvalid:
        service._session.rollback()
        auth_error(401, "session_expired", "The owner session is invalid or expired.")


def csrf_principal(
    request: Request,
    principal: AuthPrincipal = Depends(current_principal),
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    service: AuthenticationService = Depends(get_auth_service),
) -> AuthPrincipal:
    require_trusted_origin(request, get_auth_settings(request))
    if not csrf_token:
        auth_error(403, "csrf_invalid", "CSRF validation failed.")
    try:
        service.verify_csrf(principal, csrf_token)
        service._session.commit()
        return principal
    except CsrfInvalid:
        auth_error(403, "csrf_invalid", "CSRF validation failed.")


def require_permission(permission: str) -> Callable[..., AuthPrincipal]:
    def dependency(principal: AuthPrincipal = Depends(csrf_principal)) -> AuthPrincipal:
        if permission not in principal.permissions:
            auth_error(403, "permission_denied", "Permission is required.")
        return principal
    return dependency


def require_read_permission(permission: str) -> Callable[..., AuthPrincipal]:
    """Authorize an owner-session GET without requiring a CSRF header."""
    def dependency(principal: AuthPrincipal = Depends(current_principal)) -> AuthPrincipal:
        if permission not in principal.permissions:
            auth_error(403, "permission_denied", "Permission is required.")
        return principal
    return dependency


def session_response(principal: AuthPrincipal, csrf_token: str) -> SessionResponse:
    return SessionResponse(user_id=str(principal.user_id), email=principal.email, display_name=principal.display_name, organization_id=str(principal.organization_id), role=principal.role, permissions=sorted(principal.permissions), csrf_token=csrf_token)


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, response: Response, request: Request, _: None = Depends(require_trusted_origin), service: AuthenticationService = Depends(get_auth_service), settings: AuthSettings = Depends(get_auth_settings), now: datetime = Depends(utc_now)) -> SessionResponse:
    enforce_limit(service, LOGIN_IP, client_identifier(request), now)
    enforce_limit(service, LOGIN_ACCOUNT, payload.email, now)
    try:
        issued = service.login(payload.email.strip().lower(), payload.password, now=now, user_agent=request.headers.get("user-agent"), allowed_roles=frozenset({"owner", "manager", "staff"}))
    except EmailVerificationRequired as error:
        auth_error(403, error.code, str(error))
    except (InvalidCredentialsError, MembershipInactive, AuthenticationError):
        auth_error(401, "authentication_failed", "Email or password is invalid.")
    except (IdentityProviderError, SQLAlchemyError):
        auth_error(503, "authentication_unavailable", "Owner authentication is unavailable.")
    response.set_cookie(settings.session_cookie_name, issued.token, max_age=settings.session_absolute_hours * 3600, secure=settings.secure_cookies, httponly=True, samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return session_response(issued.principal, issued.csrf_token)


@router.get("/session", response_model=SessionResponse)
def read_session(request: Request, service: AuthenticationService = Depends(get_auth_service), settings: AuthSettings = Depends(get_auth_settings), now: datetime = Depends(utc_now)) -> SessionResponse:
    reject_client_tenant_context(request)
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        auth_error(401, "unauthenticated", "Authentication is required.")
    try:
        principal, csrf = service.rotate_csrf(token, now=now)
        return session_response(principal, csrf)
    except SessionInvalid:
        auth_error(401, "session_expired", "The owner session is invalid or expired.")


@router.get("/organizations", response_model=list[AuthorizedOrganizationResponse])
def authorized_organizations(
    principal: AuthPrincipal = Depends(current_principal),
    service: AuthenticationService = Depends(get_auth_service),
) -> list[AuthorizedOrganizationResponse]:
    return [
        AuthorizedOrganizationResponse(
            membership_id=membership.id,
            organization_id=organization.id,
            organization_slug=organization.slug,
            organization_name=organization.name,
            role=role.key,
        )
        for membership, organization, role in service.workforce_organizations(principal)
    ]


@router.post("/organizations/{membership_id}/select", response_model=SessionResponse)
def select_organization(
    membership_id: UUID,
    response: Response,
    request: Request,
    principal: AuthPrincipal = Depends(csrf_principal),
    service: AuthenticationService = Depends(get_auth_service),
    settings: AuthSettings = Depends(get_auth_settings),
    now: datetime = Depends(utc_now),
) -> SessionResponse:
    try:
        issued = service.switch_membership(
            principal, membership_id, now=now,
            user_agent=request.headers.get("user-agent"),
        )
    except MembershipInactive:
        auth_error(403, "membership_inactive", "The selected organization is not authorized.")
    response.set_cookie(settings.session_cookie_name, issued.token, max_age=settings.session_absolute_hours * 3600, secure=settings.secure_cookies, httponly=True, samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return session_response(issued.principal, issued.csrf_token)


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response, principal: AuthPrincipal = Depends(csrf_principal), service: AuthenticationService = Depends(get_auth_service), settings: AuthSettings = Depends(get_auth_settings), now: datetime = Depends(utc_now)) -> MessageResponse:
    service.logout(principal, now=now)
    response.delete_cookie(settings.session_cookie_name, secure=settings.secure_cookies, httponly=True, samesite="lax", path="/")
    return MessageResponse(message="Signed out.")


@router.post("/password-reset", response_model=MessageResponse)
def request_password_reset(payload: PasswordResetRequest, request: Request, _: None = Depends(require_trusted_origin), service: AuthenticationService = Depends(get_auth_service), settings: AuthSettings = Depends(get_auth_settings), now: datetime = Depends(utc_now)) -> MessageResponse:
    enforce_limit(service, RESET_REQUEST_IP, client_identifier(request), now)
    enforce_limit(service, RESET_REQUEST_ACCOUNT, payload.email, now)
    try:
        service.request_password_reset(payload.email, f"{settings.frontend_url.rstrip('/')}/admin/reset-password")
    except IdentityProviderError:
        pass
    return MessageResponse(message="If the account exists, password reset instructions have been sent.")


@router.post("/password-reset/complete", response_model=MessageResponse)
def complete_password_reset(payload: PasswordCompletionRequest, request: Request, _: None = Depends(require_trusted_origin), service: AuthenticationService = Depends(get_auth_service), now: datetime = Depends(utc_now)) -> MessageResponse:
    enforce_limit(service, RESET_COMPLETE_IP, client_identifier(request), now)
    enforce_limit(service, RESET_COMPLETE_TOKEN, payload.token_hash, now)
    try:
        service.complete_password_reset(payload.token_hash, payload.password, now=now)
    except (IdentityProviderError, AuthenticationError):
        auth_error(400, "password_reset_invalid", "Password reset link is invalid or expired.")
    except SQLAlchemyError:
        auth_error(503, "authentication_unavailable", "Owner authentication is unavailable.")
    return MessageResponse(message="Password updated. Sign in again.")


@router.post("/invitations/accept", response_model=MessageResponse)
def accept_invitation(payload: InvitationAcceptRequest, request: Request, _: None = Depends(require_trusted_origin), service: AuthenticationService = Depends(get_auth_service), now: datetime = Depends(utc_now)) -> MessageResponse:
    enforce_limit(service, INVITE_ACCEPT_IP, client_identifier(request), now)
    enforce_limit(service, INVITE_ACCEPT_INVITATION, str(payload.invitation_id), now)
    try:
        service.accept_invitation(payload.invitation_id, payload.invitation_secret, payload.token_hash, payload.password, payload.display_name, now=now)
    except (IdentityProviderError, AuthenticationError, SQLAlchemyError, ValueError):
        auth_error(400, "invitation_invalid", "Invitation is invalid or expired.")
    return MessageResponse(message="Invitation accepted. You may sign in.")


@router.post("/invitations", response_model=MessageResponse, status_code=201)
def create_invitation(payload: InvitationCreateRequest, principal: AuthPrincipal = Depends(require_permission("members.invite")), service: AuthenticationService = Depends(get_auth_service), now: datetime = Depends(utc_now)) -> MessageResponse:
    enforce_limit(service, INVITE_CREATE_ACTOR, str(principal.user_id), now)
    enforce_limit(service, INVITE_CREATE_ORGANIZATION, str(principal.organization_id), now)
    try:
        service.create_invitation(payload.email, payload.role, now=now, invited_by=principal)
    except (IdentityProviderError, SQLAlchemyError, ValueError):
        auth_error(409, "invitation_failed", "Invitation could not be created.")
    return MessageResponse(message="Invitation sent.")


@router.post("/logout-all", response_model=MessageResponse)
def logout_all(response: Response, principal: AuthPrincipal = Depends(csrf_principal), service: AuthenticationService = Depends(get_auth_service), settings: AuthSettings = Depends(get_auth_settings), now: datetime = Depends(utc_now)) -> MessageResponse:
    service.logout_all(principal, now=now)
    response.delete_cookie(settings.session_cookie_name, secure=settings.secure_cookies, httponly=True, samesite="lax", path="/")
    return MessageResponse(message="Signed out on all devices.")
