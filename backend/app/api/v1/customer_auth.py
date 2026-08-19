from datetime import datetime
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.owner_auth import (
    auth_error, client_identifier, enforce_limit, require_trusted_origin,
    session_response,
)
from app.jds_auth.config import AuthSettings
from app.jds_auth.provider import IdentityProviderError, InvalidCredentialsError
from app.jds_auth.rate_limit import LOGIN_ACCOUNT, LOGIN_IP, RESET_COMPLETE_IP, RESET_COMPLETE_TOKEN, RESET_REQUEST_ACCOUNT, RESET_REQUEST_IP, VERIFICATION_RESEND_ACCOUNT, VERIFICATION_RESEND_IP
from app.jds_auth.schemas import (
    CustomerLoginRequest, CustomerPasswordCompletionRequest, CustomerRegistrationRequest, EmailVerificationRequest,
    MessageResponse, PasswordResetRequest, SessionResponse,
)
from app.jds_auth.service import (
    AuthPrincipal, AuthenticationError, AuthenticationService, CsrfInvalid,
    EmailVerificationRequired, MembershipInactive, SessionInvalid, utc_now,
)
from app.db.session import get_db_session
from app.tenancy.resolver import TenantResolutionError, resolve_storefront_context

router = APIRouter(prefix="/customer/auth", tags=["customer-auth"])
logger = logging.getLogger(__name__)
CUSTOMER_EXPERIENCE_ROLES = frozenset({"customer", "owner"})
CUSTOMER_LOGIN_ROLES = frozenset({"customer"})


def get_customer_auth_settings(request: Request) -> AuthSettings:
    settings = request.app.state.auth_settings
    provider = request.app.state.auth_provider
    if settings is None or provider is None:
        logger.error(
            "customer_auth_configuration_unavailable settings=%s provider=%s",
            settings is not None,
            provider is not None,
        )
        auth_error(503, "authentication_unavailable", "Customer authentication is unavailable.")
    return settings


def get_customer_auth_service(
    request: Request,
    session: Session = Depends(get_db_session),
) -> AuthenticationService:
    settings = get_customer_auth_settings(request)
    try:
        storefront = resolve_storefront_context(
            session, host=request.url.hostname, frontend_url=settings.frontend_url,
            headers=request.headers, query_params=request.query_params,
        )
    except TenantResolutionError:
        auth_error(404, "tenant_not_found", "Storefront is unavailable.")
    # Tenant resolution is a read, but SQLAlchemy autobegins a transaction.
    # Authentication services deliberately own their transaction boundaries.
    session.commit()
    return AuthenticationService(
        session,
        request.app.state.auth_provider,
        settings,
        organization_id=storefront.organization_id,
    )


def require_customer_trusted_origin(request: Request, session: Session = Depends(get_db_session)) -> None:
    require_trusted_origin(request, get_customer_auth_settings(request), session)


def current_customer(
    request: Request,
    service: AuthenticationService = Depends(get_customer_auth_service),
    settings: AuthSettings = Depends(get_customer_auth_settings),
    now: datetime = Depends(utc_now),
) -> AuthPrincipal:
    token = request.cookies.get(settings.customer_session_cookie_name)
    if not token:
        auth_error(401, "unauthenticated", "Authentication is required.")
    try:
        principal = service.resolve(token, now=now)
        storefront = resolve_storefront_context(
            service._session, host=request.headers.get("host"),
            frontend_url=settings.frontend_url, headers=request.headers,
            query_params=request.query_params,
        )
        if storefront.organization_id != principal.organization_id:
            raise SessionInvalid("Customer session does not belong to this storefront.")
        if principal.role not in CUSTOMER_EXPERIENCE_ROLES:
            auth_error(403, "customer_required", "A customer account is required.")
        service._session.commit()
        return principal
    except (SessionInvalid, TenantResolutionError):
        service._session.rollback()
        auth_error(401, "session_expired", "The customer session is invalid or expired.")


def current_ordering_customer(
    principal: AuthPrincipal = Depends(current_customer),
) -> AuthPrincipal:
    """Require the dedicated customer role for order and payment mutations."""
    if principal.role != "customer":
        auth_error(403, "customer_required", "A customer account is required.")
    return principal


def optional_customer(
    request: Request,
    session: Session = Depends(get_db_session),
    now: datetime = Depends(utc_now),
) -> AuthPrincipal | None:
    settings = request.app.state.auth_settings
    provider = request.app.state.auth_provider
    if settings is None or provider is None:
        return None
    token = request.cookies.get(settings.customer_session_cookie_name)
    if not token:
        return None
    service = AuthenticationService(session, provider, settings)
    try:
        principal = service.resolve(token, now=now)
        storefront = resolve_storefront_context(
            service._session, host=request.headers.get("host"),
            frontend_url=settings.frontend_url, headers=request.headers,
            query_params=request.query_params,
        )
        if storefront.organization_id != principal.organization_id:
            return None
        if principal.role not in CUSTOMER_EXPERIENCE_ROLES:
            return None
        service._session.commit()
        return principal
    except (SessionInvalid, TenantResolutionError):
        service._session.rollback()
        return None


def customer_csrf(
    request: Request,
    principal: AuthPrincipal = Depends(current_customer),
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    service: AuthenticationService = Depends(get_customer_auth_service),
) -> AuthPrincipal:
    require_trusted_origin(request, get_customer_auth_settings(request), service._session)
    if not csrf_token:
        auth_error(403, "csrf_invalid", "CSRF validation failed.")
    try:
        service.verify_csrf(principal, csrf_token)
        service._session.commit()
        return principal
    except CsrfInvalid:
        auth_error(403, "csrf_invalid", "CSRF validation failed.")


@router.post("/register", response_model=MessageResponse, status_code=201)
def register(payload: CustomerRegistrationRequest, request: Request, _: None = Depends(require_customer_trusted_origin), service: AuthenticationService = Depends(get_customer_auth_service), now: datetime = Depends(utc_now)) -> MessageResponse:
    enforce_limit(service, LOGIN_IP, client_identifier(request), now)
    enforce_limit(service, LOGIN_ACCOUNT, payload.email, now)
    try:
        service.register_customer(payload.email, payload.password, payload.display_name, payload.phone, now=now)
        return MessageResponse(message="Check your email to verify your account.")
    except (AuthenticationError, ValueError) as error:
        logger.error(
            "customer_registration_failed stage=%s exception_type=%s reason=%s",
            getattr(error, "stage", "registration_business_rule"),
            type(error).__name__,
            getattr(error, "reason", "authentication_error"),
        )
        auth_error(409, "registration_failed", "Customer account could not be created.")
    except IdentityProviderError:
        logger.exception("customer_registration_failed stage=supabase_registration")
        auth_error(503, "authentication_unavailable", "Customer registration is unavailable.")
    except SQLAlchemyError as error:
        logger.exception(
            "customer_registration_failed stage=%s exception_type=%s reason=database_error",
            service.registration_stage,
            type(error).__name__,
        )
        auth_error(503, "authentication_unavailable", "Customer registration is unavailable.")


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(payload: EmailVerificationRequest, _: None = Depends(require_customer_trusted_origin), service: AuthenticationService = Depends(get_customer_auth_service), now: datetime = Depends(utc_now)) -> MessageResponse:
    try:
        service.verify_customer_email(payload.token_hash, now=now)
        return MessageResponse(message="Email verified. You may sign in.")
    except (AuthenticationError, IdentityProviderError, SQLAlchemyError) as error:
        logger.error(
            "customer_verification_failed stage=%s exception_type=%s "
            "provider_status=%s provider_code=%s provider_message=%r "
            "business_rule=%s",
            getattr(error, "stage", service.verification_stage),
            type(error).__name__,
            getattr(error, "provider_status", None),
            getattr(error, "provider_code", None),
            getattr(error, "provider_message", None),
            getattr(error, "reason", None),
        )
        auth_error(400, "verification_invalid", "Email verification link is invalid or expired.")


@router.post("/verification/resend", response_model=MessageResponse)
def resend_verification(payload: PasswordResetRequest, request: Request, _: None = Depends(require_customer_trusted_origin), service: AuthenticationService = Depends(get_customer_auth_service), now: datetime = Depends(utc_now)) -> MessageResponse:
    enforce_limit(service, VERIFICATION_RESEND_IP, client_identifier(request), now)
    enforce_limit(service, VERIFICATION_RESEND_ACCOUNT, payload.email, now)
    try:
        service.resend_customer_verification(payload.email)
    except IdentityProviderError:
        pass
    return MessageResponse(message="If an unverified account exists, a verification email has been sent.")


@router.post("/login", response_model=SessionResponse)
def login(payload: CustomerLoginRequest, response: Response, request: Request, _: None = Depends(require_customer_trusted_origin), service: AuthenticationService = Depends(get_customer_auth_service), settings: AuthSettings = Depends(get_customer_auth_settings), now: datetime = Depends(utc_now)) -> SessionResponse:
    enforce_limit(service, LOGIN_IP, client_identifier(request), now)
    enforce_limit(service, LOGIN_ACCOUNT, payload.email, now)
    try:
        issued = service.login(payload.email.strip().lower(), payload.password, now=now, user_agent=request.headers.get("user-agent"), allowed_roles=CUSTOMER_LOGIN_ROLES, persistent=payload.keep_signed_in)
    except EmailVerificationRequired as error:
        auth_error(403, error.code, str(error))
    except (InvalidCredentialsError, MembershipInactive, AuthenticationError):
        auth_error(401, "authentication_failed", "Email or password is invalid.")
    except (IdentityProviderError, SQLAlchemyError):
        auth_error(503, "authentication_unavailable", "Customer authentication is unavailable.")
    cookie_max_age = (
        settings.customer_persistent_session_days * 24 * 3600
        if payload.keep_signed_in
        else settings.session_absolute_hours * 3600
    )
    response.set_cookie(settings.customer_session_cookie_name, issued.token, max_age=cookie_max_age, secure=settings.secure_cookies, httponly=True, samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return session_response(issued.principal, issued.csrf_token)


@router.get("/session", response_model=SessionResponse)
def read_session(request: Request, service: AuthenticationService = Depends(get_customer_auth_service), settings: AuthSettings = Depends(get_customer_auth_settings), now: datetime = Depends(utc_now)) -> SessionResponse:
    token = request.cookies.get(settings.customer_session_cookie_name)
    if not token:
        auth_error(401, "unauthenticated", "Authentication is required.")
    try:
        principal, csrf = service.rotate_csrf(token, now=now)
        storefront = resolve_storefront_context(
            service._session, host=request.headers.get("host"),
            frontend_url=settings.frontend_url, headers=request.headers,
            query_params=request.query_params,
        )
        if storefront.organization_id != principal.organization_id:
            raise SessionInvalid("Customer session does not belong to this storefront.")
        if principal.role not in CUSTOMER_EXPERIENCE_ROLES:
            auth_error(403, "customer_required", "A customer account is required.")
        return session_response(principal, csrf)
    except (SessionInvalid, TenantResolutionError):
        auth_error(401, "session_expired", "The customer session is invalid or expired.")


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response, principal: AuthPrincipal = Depends(customer_csrf), service: AuthenticationService = Depends(get_customer_auth_service), settings: AuthSettings = Depends(get_customer_auth_settings), now: datetime = Depends(utc_now)) -> MessageResponse:
    service.logout(principal, now=now)
    response.delete_cookie(settings.customer_session_cookie_name, secure=settings.secure_cookies, httponly=True, samesite="lax", path="/")
    return MessageResponse(message="Signed out.")


@router.post("/password-reset", response_model=MessageResponse)
def request_password_reset(payload: PasswordResetRequest, request: Request, _: None = Depends(require_customer_trusted_origin), service: AuthenticationService = Depends(get_customer_auth_service), settings: AuthSettings = Depends(get_customer_auth_settings), now: datetime = Depends(utc_now)) -> MessageResponse:
    enforce_limit(service, RESET_REQUEST_IP, client_identifier(request), now)
    enforce_limit(service, RESET_REQUEST_ACCOUNT, payload.email, now)
    try:
        service.request_password_reset(payload.email, f"{settings.frontend_url.rstrip('/')}/account/reset-password")
    except IdentityProviderError:
        pass
    return MessageResponse(message="If the account exists, password reset instructions have been sent.")


@router.post("/password-reset/complete", response_model=MessageResponse)
def complete_password_reset(payload: CustomerPasswordCompletionRequest, request: Request, _: None = Depends(require_customer_trusted_origin), service: AuthenticationService = Depends(get_customer_auth_service), now: datetime = Depends(utc_now)) -> MessageResponse:
    enforce_limit(service, RESET_COMPLETE_IP, client_identifier(request), now)
    recovery_credential = payload.token_hash or payload.access_token
    assert recovery_credential is not None
    enforce_limit(service, RESET_COMPLETE_TOKEN, recovery_credential, now)
    try:
        service.complete_password_reset(payload.token_hash, payload.password, access_token=payload.access_token, now=now)
        return MessageResponse(message="Password updated. Sign in again.")
    except (AuthenticationError, IdentityProviderError, SQLAlchemyError) as error:
        logger.warning(
            "customer_password_reset_failure_response stage=%s response_code=password_reset_invalid",
            service.password_reset_stage,
        )
        logger.error(
            "customer_password_reset_failed stage=%s exception_type=%s "
            "provider_operation=%s provider_method=%s provider_status=%s "
            "provider_code=%s provider_message=%r",
            service.password_reset_stage,
            type(error).__name__,
            getattr(error, "provider_operation", None),
            getattr(error, "provider_method", None),
            getattr(error, "provider_status", None),
            getattr(error, "provider_code", None),
            getattr(error, "provider_message", None),
        )
        auth_error(400, "password_reset_invalid", "Password reset link is invalid or expired.")
