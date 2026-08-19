import os
from dataclasses import dataclass
from urllib.parse import urlparse

from cryptography.fernet import Fernet


class CloverConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CloverSettings:
    app_id: str
    app_secret: str
    token_encryption_key: str
    state_secret: str
    webhook_secret: str
    public_app_url: str
    frontend_url: str
    merchant_id: str
    environment: str = "sandbox"
    page_config_uuid: str | None = None
    ecommerce_private_token: str | None = None

    @classmethod
    def from_env(cls) -> "CloverSettings":
        return cls(
            app_id=os.getenv("CLOVER_APP_ID", ""),
            app_secret=os.getenv("CLOVER_APP_SECRET", ""),
            token_encryption_key=os.getenv("CLOVER_TOKEN_ENCRYPTION_KEY", ""),
            state_secret=os.getenv("CLOVER_STATE_SECRET", ""),
            webhook_secret=os.getenv("CLOVER_WEBHOOK_SECRET", ""),
            public_app_url=os.getenv("PUBLIC_APP_URL", ""),
            frontend_url=os.getenv("FRONTEND_URL", ""),
            environment=os.getenv("CLOVER_ENVIRONMENT", "sandbox").lower(),
            page_config_uuid=os.getenv("CLOVER_PAGE_CONFIG_UUID") or None,
            merchant_id=os.getenv("CLOVER_MERCHANT_ID", ""),
            ecommerce_private_token=(
                os.getenv("CLOVER_ECOMMERCE_PRIVATE_TOKEN") or None
            ),
        )

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("CLOVER_APP_ID", self.app_id),
                ("CLOVER_APP_SECRET", self.app_secret),
                ("CLOVER_TOKEN_ENCRYPTION_KEY", self.token_encryption_key),
                ("CLOVER_STATE_SECRET", self.state_secret),
                ("CLOVER_WEBHOOK_SECRET", self.webhook_secret),
                ("CLOVER_MERCHANT_ID", self.merchant_id),
                ("PUBLIC_APP_URL", self.public_app_url),
                ("FRONTEND_URL", self.frontend_url),
            )
            if not value
        ]
        if missing:
            raise CloverConfigurationError(
                f"Missing Clover configuration: {', '.join(missing)}."
            )
        if self.environment not in {"sandbox", "production"}:
            raise CloverConfigurationError(
                "CLOVER_ENVIRONMENT must be sandbox or production."
            )
        if self.environment == "production" and self.ecommerce_private_token:
            raise CloverConfigurationError(
                "Production Clover configuration requires OAuth; "
                "CLOVER_ECOMMERCE_PRIVATE_TOKEN must be unset."
            )
        if self.page_config_uuid is not None:
            if (
                not self.page_config_uuid.strip()
                or self.page_config_uuid != self.page_config_uuid.strip()
                or any(character.isspace() for character in self.page_config_uuid)
            ):
                raise CloverConfigurationError(
                    "CLOVER_PAGE_CONFIG_UUID must be a non-blank identifier "
                    "without whitespace."
                )
        if len(self.state_secret) < 32 or len(self.webhook_secret) < 32:
            raise CloverConfigurationError(
                "CLOVER_STATE_SECRET and CLOVER_WEBHOOK_SECRET must be at least "
                "32 characters."
            )
        if self.state_secret == self.webhook_secret:
            raise CloverConfigurationError(
                "CLOVER_STATE_SECRET and CLOVER_WEBHOOK_SECRET must be different."
            )
        try:
            Fernet(self.token_encryption_key.encode())
        except (TypeError, ValueError) as error:
            raise CloverConfigurationError(
                "CLOVER_TOKEN_ENCRYPTION_KEY must be a valid Fernet key."
            ) from error
        for name, value in (
            ("PUBLIC_APP_URL", self.public_app_url),
            ("FRONTEND_URL", self.frontend_url),
        ):
            parsed = urlparse(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.params
                or parsed.query
                or parsed.fragment
            ):
                raise CloverConfigurationError(
                    f"{name} must be an HTTPS origin without credentials, path, "
                    "query, or fragment."
                )

    @property
    def authorize_base_url(self) -> str:
        if self.environment == "sandbox":
            return "https://sandbox.dev.clover.com"
        return "https://www.clover.com"

    @property
    def api_base_url(self) -> str:
        return self.platform_api_base_url

    @property
    def platform_api_base_url(self) -> str:
        if self.environment == "sandbox":
            return "https://apisandbox.dev.clover.com"
        return "https://api.clover.com"

    @property
    def ecommerce_service_base_url(self) -> str:
        if self.environment == "sandbox":
            return "https://scl-sandbox.dev.clover.com"
        return "https://scl.clover.com"

    @property
    def tokenization_base_url(self) -> str:
        if self.environment == "sandbox":
            return "https://token-sandbox.dev.clover.com"
        return "https://token.clover.com"

    @property
    def hosted_checkout_base_url(self) -> str:
        """Hosted Checkout is documented on Clover's Platform API host."""
        return self.platform_api_base_url

    @property
    def credential_source(self) -> str:
        return "sandbox_private_token" if self.ecommerce_private_token else "oauth"

    @property
    def callback_url(self) -> str:
        return f"{self.public_app_url.rstrip('/')}/api/v1/clover/oauth/callback"

    @property
    def launch_url(self) -> str:
        return f"{self.public_app_url.rstrip('/')}/api/v1/clover/oauth/start"
