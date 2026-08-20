"""Fail-closed configuration for the persistent synthetic staging review."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse


STAGING_OWNER_EMAIL = "owner@staging-review.jds.invalid"
STAGING_AUTH_ISSUER = "https://staging-review-auth.jds.invalid"
STAGING_AUTH_SUBJECT = "jds-staging-review-owner"
STAGING_SEED_CONFIRMATION = "seed-synthetic-staging-review"
STAGING_APPLICATION_SUFFIX = "-staging-review"
STAGING_DATABASE_SUFFIX = "_staging_review"

PRODUCTION_CREDENTIAL_NAMES = (
    "SUPABASE_AUTH_URL",
    "SUPABASE_AUTH_PUBLISHABLE_KEY",
    "SUPABASE_AUTH_SECRET_KEY",
    "CLOVER_APP_ID",
    "CLOVER_APP_SECRET",
    "CLOVER_ECOMMERCE_PRIVATE_TOKEN",
    "CLOVER_MERCHANT_ID",
    "CLOVER_PAGE_CONFIG_UUID",
    "CLOVER_TOKEN_ENCRYPTION_KEY",
    "CLOVER_STATE_SECRET",
    "CLOVER_WEBHOOK_SECRET",
    "WEB_PUSH_VAPID_PRIVATE_KEY",
    "WEB_PUSH_VAPID_PUBLIC_KEY",
    "WEB_PUSH_SUBSCRIPTION_ENCRYPTION_KEY",
)


def staging_review_requested() -> bool:
    return os.getenv("JDS_ENABLE_STAGING_REVIEW", "false").lower() == "true"


def staging_review_enabled() -> bool:
    return os.getenv("JDS_ENVIRONMENT", "").strip().lower() == "staging" and staging_review_requested()


def staging_allowed_hosts() -> frozenset[str]:
    return frozenset(
        item.strip().lower().rstrip(".")
        for item in os.getenv("JDS_STAGING_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    )


def database_name(database_url: str) -> str:
    parsed = urlparse(database_url.replace("postgresql+psycopg", "postgresql", 1))
    return (parsed.path or "").lstrip("/")


def assert_staging_database(database_url: str) -> None:
    parsed = urlparse(database_url.replace("postgresql+psycopg", "postgresql", 1))
    name = database_name(database_url).lower()
    host = (parsed.hostname or "").lower()
    if not host or not name.endswith(STAGING_DATABASE_SUFFIX):
        raise RuntimeError("Staging review requires a positively identified staging review database.")
    production_markers = ("production", "-prod", "_prod", ".prod")
    if any(marker in host or marker in name for marker in production_markers):
        raise RuntimeError("Staging review refuses a database with production indicators.")


def validate_staging_runtime(database_url: str) -> tuple[str, str, frozenset[str]]:
    environment = os.getenv("JDS_ENVIRONMENT", "").strip().lower()
    if staging_review_requested() and environment == "production":
        raise RuntimeError("Production refuses staging review mode.")
    if environment != "staging" or not staging_review_requested():
        raise RuntimeError("Staging authentication requires explicit staging review mode.")
    if os.getenv("JDS_AUTH_PROVIDER", "").strip().lower() != "staging-review":
        raise RuntimeError("Staging review requires its dedicated identity provider.")
    if os.getenv("JDS_ENABLE_LOCAL_REVIEW", "false").lower() == "true":
        raise RuntimeError("Staging review refuses localhost development review mode.")
    if any(os.getenv(name, "").strip() for name in PRODUCTION_CREDENTIAL_NAMES):
        raise RuntimeError("Staging review refuses production authentication, payment, or push credentials.")
    if os.getenv("JDS_OUTBOUND_INTEGRATIONS_ENABLED", "false").lower() != "false":
        raise RuntimeError("Staging review requires outbound integrations to be disabled.")
    if os.getenv("JDS_PAYMENT_MODE", "").strip().lower() != "fixture-disabled":
        raise RuntimeError("Staging review requires fixture-only disabled payments.")
    if os.getenv("PUSH_ENROLLMENT_ENABLED", "false").lower() == "true" or os.getenv("PUSH_RELEASE_ENABLED", "false").lower() == "true":
        raise RuntimeError("Staging review refuses Web Push activation.")
    assert_staging_database(database_url)
    application_key = os.getenv("JDS_APPLICATION_KEY", "").strip()
    instance_id = os.getenv("JDS_STAGING_INSTANCE_ID", "").strip()
    if not application_key.endswith(STAGING_APPLICATION_SUFFIX) or len(instance_id) < 16:
        raise RuntimeError("Staging review requires staging-specific application and instance identifiers.")
    frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")
    parsed_frontend = urlparse(frontend_url)
    hosts = staging_allowed_hosts()
    if (
        parsed_frontend.scheme != "https"
        or not parsed_frontend.hostname
        or parsed_frontend.hostname.lower() not in hosts
        or parsed_frontend.username
        or parsed_frontend.password
        or parsed_frontend.path not in {"", "/"}
        or parsed_frontend.query
        or parsed_frontend.fragment
    ):
        raise RuntimeError("Staging review requires an exact allowed HTTPS frontend origin.")
    public_app_url = os.getenv("PUBLIC_APP_URL", "").rstrip("/")
    parsed_api = urlparse(public_app_url)
    if (
        parsed_api.scheme != "https"
        or not parsed_api.hostname
        or not parsed_api.hostname.lower().endswith(".onrender.com")
        or parsed_api.username
        or parsed_api.password
        or parsed_api.path not in {"", "/"}
        or parsed_api.query
        or parsed_api.fragment
    ):
        raise RuntimeError("Staging review requires a dedicated HTTPS Render API origin.")
    password = os.getenv("JDS_STAGING_AUTH_PASSWORD", "")
    if len(password) < 20:
        raise RuntimeError("Staging review requires a strong configured review password.")
    return frontend_url, password, hosts


def validate_staging_media_root() -> Path:
    raw = os.getenv("JDS_LOCAL_MEDIA_ROOT", "").strip()
    if not raw:
        raise RuntimeError("Staging review requires a persistent media root.")
    root = Path(raw)
    if not root.is_absolute() or root == Path("/") or root == Path("/tmp") or Path("/tmp") in root.parents:
        raise RuntimeError("Staging review media must use a dedicated absolute persistent path.")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    probe = root / ".jds-staging-write-check"
    try:
        probe.write_text("staging-media-ready", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        raise RuntimeError("Staging review media root is not writable.") from error
    return root.resolve()


def assert_staging_seed_safe(database_url: str) -> None:
    if not staging_review_enabled():
        raise RuntimeError("Staging seed requires explicit staging review mode.")
    if os.getenv("JDS_STAGING_SEED_CONFIRMATION", "") != STAGING_SEED_CONFIRMATION:
        raise RuntimeError("Staging seed requires explicit synthetic-data confirmation.")
    validate_staging_runtime(database_url)
