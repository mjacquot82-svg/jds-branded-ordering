import os
from dataclasses import dataclass
from urllib.parse import urlparse


class AuthConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthSettings:
    supabase_url: str
    supabase_publishable_key: str
    supabase_secret_key: str
    session_pepper: str
    frontend_url: str
    application_key: str = "jds-commerce"
    organization_slug: str = "the-guest-house"
    session_cookie_name: str = "__Host-jds_owner_session"
    customer_session_cookie_name: str = "__Host-jds_customer_session"
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    customer_persistent_session_days: int = 30
    secure_cookies: bool = True

    @classmethod
    def from_env(cls) -> "AuthSettings":
        return cls(
            supabase_url=os.getenv("SUPABASE_AUTH_URL", ""),
            supabase_publishable_key=os.getenv("SUPABASE_AUTH_PUBLISHABLE_KEY", ""),
            supabase_secret_key=os.getenv("SUPABASE_AUTH_SECRET_KEY", ""),
            session_pepper=os.getenv("JDS_AUTH_SESSION_PEPPER", ""),
            frontend_url=os.getenv("FRONTEND_URL", ""),
            application_key=os.getenv("JDS_APPLICATION_KEY", "jds-commerce"),
            organization_slug=os.getenv("JDS_ORGANIZATION_SLUG", "the-guest-house"),
            customer_persistent_session_days=int(
                os.getenv("JDS_CUSTOMER_PERSISTENT_SESSION_DAYS", "30")
            ),
            secure_cookies=os.getenv("JDS_AUTH_SECURE_COOKIES", "true").lower()
            != "false",
        )

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("SUPABASE_AUTH_URL", self.supabase_url),
                ("SUPABASE_AUTH_PUBLISHABLE_KEY", self.supabase_publishable_key),
                ("SUPABASE_AUTH_SECRET_KEY", self.supabase_secret_key),
                ("JDS_AUTH_SESSION_PEPPER", self.session_pepper),
                ("FRONTEND_URL", self.frontend_url),
            )
            if not value
        ]
        if missing:
            raise AuthConfigurationError(
                f"Missing JDS authentication configuration: {', '.join(missing)}."
            )
        if len(self.session_pepper) < 32:
            raise AuthConfigurationError(
                "JDS_AUTH_SESSION_PEPPER must be at least 32 characters."
            )
        if self.customer_persistent_session_days < 1:
            raise AuthConfigurationError(
                "JDS_CUSTOMER_PERSISTENT_SESSION_DAYS must be at least 1."
            )
        frontend_host = urlparse(self.frontend_url).hostname
        if not self.secure_cookies and frontend_host not in {"localhost", "test"}:
            raise AuthConfigurationError(
                "Insecure authentication cookies are allowed only for local tests."
            )
        for name, value in (
            ("SUPABASE_AUTH_URL", self.supabase_url),
            ("FRONTEND_URL", self.frontend_url),
        ):
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.hostname:
                if not (
                    not self.secure_cookies
                    and parsed.scheme == "http"
                    and parsed.hostname in {"localhost", "test"}
                ):
                    raise AuthConfigurationError(f"{name} must be an HTTPS origin.")
            if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
                raise AuthConfigurationError(f"{name} must be an origin without credentials or query.")
            if parsed.path not in {"", "/"}:
                raise AuthConfigurationError(f"{name} must not contain a path.")
