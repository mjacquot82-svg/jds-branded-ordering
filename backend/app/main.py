import os
import asyncio
from contextlib import suppress
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from app.api.v1.router import router as api_v1_router
from app.db.engine import create_database_engine
from app.db.health import database_is_available
from app.db.session import create_session_factory
from app.jds_auth.config import AuthSettings
from app.jds_auth.provider import IdentityProvider, SupabaseIdentityProvider
from app.push.config import PushSettings
from app.push.trigger import drain_push_outbox

APP_NAME = "guesthouse-backend"
APP_VERSION = "0.1.0"


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
    resolved_auth_settings = auth_settings
    if resolved_auth_settings is None:
        candidate = AuthSettings.from_env()
        if candidate.supabase_url:
            candidate.validate()
            resolved_auth_settings = candidate
    application.state.auth_settings = resolved_auth_settings
    application.state.auth_provider = auth_provider or (
        SupabaseIdentityProvider(resolved_auth_settings)
        if resolved_auth_settings is not None
        else None
    )
    application.state.push_settings = PushSettings.from_env()
    frontend_url = os.getenv("FRONTEND_URL") or (
        resolved_auth_settings.frontend_url if resolved_auth_settings else None
    )
    allowed_origins = [frontend_url] if frontend_url else []
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=bool(frontend_url),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token", "Idempotency-Key"],
    )
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
