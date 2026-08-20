import os
import asyncio
import re
import uuid
from contextlib import suppress
from contextlib import asynccontextmanager
from typing import AsyncIterator
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from app.api.v1.router import router as api_v1_router
from app.db.engine import create_database_engine
from app.db.health import database_is_available
from app.db.session import create_session_factory
from app.jds_auth.config import AuthSettings
from app.jds_auth.provider import DevelopmentIdentityProvider, IdentityProvider, SupabaseIdentityProvider
from app.push.config import PushSettings
from app.push.trigger import drain_push_outbox

APP_NAME = "guesthouse-backend"
APP_VERSION = "0.1.0"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def create_app(
    database_url: str | None = None,
    *,
    auth_settings: AuthSettings | None = None,
    auth_provider: IdentityProvider | None = None,
) -> FastAPI:
    resolved_database_url = database_url
    if resolved_database_url is None:
        resolved_database_url = os.getenv("DATABASE_URL")

    engine = create_database_engine(resolved_database_url) if resolved_database_url else None
    session_factory = create_session_factory(engine) if engine is not None else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async def periodic_push_drain() -> None:
            while True:
                await asyncio.to_thread(
                    drain_push_outbox,
                    session_factory,
                    application.state.push_settings,
                )
                await asyncio.sleep(60)

        push_task = asyncio.create_task(periodic_push_drain())
        try:
            yield
        finally:
            push_task.cancel()
            with suppress(asyncio.CancelledError):
                await push_task
            if engine is not None:
                engine.dispose()

    application = FastAPI(
        title="The Guest House API",
        version=APP_VERSION,
        lifespan=lifespan,
    )
    application.state.db_engine = engine
    application.state.db_session_factory = session_factory
    runtime_environment = os.getenv("JDS_ENVIRONMENT", "").strip().lower()
    auth_provider_mode = os.getenv("JDS_AUTH_PROVIDER", "supabase").strip().lower()
    local_review_enabled = os.getenv("JDS_ENABLE_LOCAL_REVIEW", "false").lower() == "true"
    local_review_origin = os.getenv("JDS_LOCAL_REVIEW_ORIGIN", "").rstrip("/")
    if auth_provider is None and auth_provider_mode == "development":
        if runtime_environment != "development" or not local_review_enabled:
            raise RuntimeError("Development authentication requires explicit local development review mode.")
        local_email = os.getenv("JDS_LOCAL_AUTH_EMAIL", "owner@local.jds.test").strip().lower()
        local_password = os.getenv("JDS_LOCAL_AUTH_PASSWORD", "")
        if local_email != "owner@local.jds.test" or len(local_password) < 15:
            raise RuntimeError("Development authentication requires the fixed local owner and a 15-character password.")
        parsed_review_origin = urlparse(local_review_origin)
        if (
            not local_review_origin
            or parsed_review_origin.scheme not in {"http", "https"}
            or not parsed_review_origin.hostname
            or parsed_review_origin.username
            or parsed_review_origin.password
            or parsed_review_origin.path not in {"", "/"}
            or parsed_review_origin.params
            or parsed_review_origin.query
            or parsed_review_origin.fragment
        ):
            raise RuntimeError("Development authentication requires an explicit local review origin.")
        if parsed_review_origin.scheme == "http" and parsed_review_origin.hostname not in {"localhost", "127.0.0.1", "test"}:
            raise RuntimeError("Non-local development review origins must use HTTPS.")

    resolved_auth_settings = auth_settings
    if resolved_auth_settings is None:
        if auth_provider_mode == "development":
            session_pepper = os.getenv("JDS_AUTH_SESSION_PEPPER", "")
            frontend_url = os.getenv("FRONTEND_URL", "")
            if len(session_pepper) < 32 or not frontend_url:
                raise RuntimeError("Local review auth requires FRONTEND_URL and a 32-character session pepper.")
            resolved_auth_settings = AuthSettings(
                supabase_url="", supabase_publishable_key="", supabase_secret_key="",
                session_pepper=session_pepper, frontend_url=frontend_url,
                secure_cookies=frontend_url.startswith("https://"),
            )
        else:
            candidate = AuthSettings.from_env()
            if candidate.supabase_url:
                candidate.validate()
                resolved_auth_settings = candidate
    application.state.auth_settings = resolved_auth_settings
    if auth_provider is not None:
        application.state.auth_provider = auth_provider
    elif auth_provider_mode == "development":
        application.state.auth_provider = DevelopmentIdentityProvider(
            email=local_email, password=local_password,
        )
    else:
        application.state.auth_provider = (
            SupabaseIdentityProvider(resolved_auth_settings)
            if resolved_auth_settings is not None else None
        )
    application.state.local_review_enabled = local_review_enabled and runtime_environment == "development"
    application.state.local_review_origin = local_review_origin if application.state.local_review_enabled else ""
    application.state.push_settings = PushSettings.from_env()
    frontend_url = os.getenv("FRONTEND_URL") or (
        resolved_auth_settings.frontend_url if resolved_auth_settings else None
    )
    allowed_origins = [origin for origin in {frontend_url, application.state.local_review_origin} if origin]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=bool(frontend_url),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "X-CSRF-Token",
            "Idempotency-Key",
            "X-Request-Id",
        ],
        expose_headers=["X-Request-Id"],
    )

    @application.middleware("http")
    async def attach_request_id(request: Request, call_next):
        candidate = request.headers.get("X-Request-Id", "")
        request_id = (
            candidate
            if REQUEST_ID_PATTERN.fullmatch(candidate)
            else str(uuid.uuid4())
        )
        request.state.request_id = request_id
        response = await call_next(request)
        local_review_tenant = request.query_params.get("review_tenant")
        if application.state.local_review_enabled and local_review_tenant in {
            "the-guest-house", "second-street-cafe",
        }:
            response.set_cookie(
                "jds_local_review_tenant", local_review_tenant,
                httponly=True, secure=False, samesite="lax", path="/",
            )
        response.headers["X-Request-Id"] = request_id
        return response

    application.include_router(api_v1_router)

    @application.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {
            "status": "ok",
            "service": APP_NAME,
            "version": APP_VERSION,
        }

    @application.get("/health/ready")
    def readiness(request: Request) -> JSONResponse:
        database_engine = request.app.state.db_engine

        if database_engine is None or not database_is_available(database_engine):
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "database": "failed",
                },
            )

        return JSONResponse(
            content={
                "status": "ready",
                "database": "ok",
            },
        )

    return application


app = create_app()
