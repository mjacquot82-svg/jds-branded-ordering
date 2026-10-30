"""Square platform configuration. Square stays inert until every value is set."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from cryptography.fernet import Fernet

SQUARE_API_VERSION = "2025-01-23"
SQUARE_OAUTH_SCOPES = (
    "MERCHANT_PROFILE_READ",
    "PAYMENTS_READ",
    "PAYMENTS_WRITE",
    "ORDERS_READ",
    "ORDERS_WRITE",
)
WEBHOOK_PATH = "/api/v1/square/webhooks"
CALLBACK_PATH = "/api/v1/square/oauth/callback"


class SquareConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SquareSettings:
    application_id: str
    application_secret: str
    webhook_signature_key: str
    token_encryption_key: str
    state_secret: str
    public_app_url: str
    frontend_url: str
    environment: str = "sandbox"
    webhook_url_override: str | None = None

    @classmethod
    def from_env(cls) -> "SquareSettings":
        return cls(
            application_id=os.getenv("JDS_SQUARE_APPLICATION_ID", "").strip(),
            application_secret=os.getenv("JDS_SQUARE_APPLICATION_SECRET", "").strip(),
            webhook_signature_key=os.getenv("JDS_SQUARE_WEBHOOK_SIGNATURE_KEY", "").strip(),
            token_encryption_key=os.getenv("JDS_SQUARE_TOKEN_ENCRYPTION_KEY", "").strip(),
            state_secret=os.getenv("JDS_SQUARE_STATE_SECRET", "").strip(),
            public_app_url=os.getenv("PUBLIC_APP_URL", "").strip(),
            frontend_url=os.getenv("FRONTEND_URL", "").strip(),
            environment=(os.getenv("JDS_SQUARE_ENVIRONMENT", "sandbox").strip().lower() or "sandbox"),
            webhook_url_override=os.getenv("JDS_SQUARE_WEBHOOK_URL", "").strip() or None,
        )

    @property
    def is_configured(self) -> bool:
        try:
            self.validate()
        except SquareConfigurationError:
            return False
        return True

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("JDS_SQUARE_APPLICATION_ID", self.application_id),
                ("JDS_SQUARE_APPLICATION_SECRET", self.application_secret),
                ("JDS_SQUARE_WEBHOOK_SIGNATURE_KEY", self.webhook_signature_key),
                ("JDS_SQUARE_TOKEN_ENCRYPTION_KEY", self.token_encryption_key),
                ("JDS_SQUARE_STATE_SECRET", self.state_secret),
                ("PUBLIC_APP_URL", self.public_app_url),
                ("FRONTEND_URL", self.frontend_url),
            )
            if not value
        ]
        if missing:
            raise SquareConfigurationError(f"Missing Square configuration: {', '.join(missing)}.")
        if self.environment not in {"sandbox", "production"}:
            raise SquareConfigurationError("JDS_SQUARE_ENVIRONMENT must be sandbox or production.")
        if self.environment == "sandbox" and not self.application_id.startswith("sandbox-"):
            raise SquareConfigurationError(
                "Sandbox mode needs a Square sandbox application ID (starts with 'sandbox-')."
            )
        if self.environment == "production" and self.application_id.startswith("sandbox-"):
            raise SquareConfigurationError("Production mode cannot use a sandbox application ID.")
        if len(self.state_secret) < 32:
            raise SquareConfigurationError("JDS_SQUARE_STATE_SECRET must be at least 32 characters.")
        try:
            Fernet(self.token_encryption_key.encode())
        except (TypeError, ValueError) as error:
            raise SquareConfigurationError(
                "JDS_SQUARE_TOKEN_ENCRYPTION_KEY must be a valid Fernet key."
            ) from error
        for name, value in (("PUBLIC_APP_URL", self.public_app_url), ("FRONTEND_URL", self.frontend_url)):
            parsed = urlparse(value)
            if (
                parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            ):
                raise SquareConfigurationError(f"{name} must be an HTTPS origin.")
        if self.webhook_url_override and urlparse(self.webhook_url_override).scheme != "https":
            raise SquareConfigurationError("JDS_SQUARE_WEBHOOK_URL must be HTTPS.")

    @property
    def api_base_url(self) -> str:
        if self.environment == "sandbox":
            return "https://connect.squareupsandbox.com"
        return "https://connect.squareup.com"

    @property
    def callback_url(self) -> str:
        return f"{self.public_app_url.rstrip('/')}{CALLBACK_PATH}"

    @property
    def webhook_url(self) -> str:
        """Exact notification URL registered in Square (part of the signed payload)."""
        return self.webhook_url_override or f"{self.public_app_url.rstrip('/')}{WEBHOOK_PATH}"
