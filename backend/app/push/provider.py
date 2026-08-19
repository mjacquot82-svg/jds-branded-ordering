import json
from dataclasses import dataclass
from typing import Callable, Protocol

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

from app.push.config import PushSettings


@dataclass(frozen=True)
class ProviderResult:
    accepted: bool
    permanent: bool
    expired: bool = False
    http_status: int | None = None
    error_code: str | None = None


class PushProvider(Protocol):
    def send(
        self,
        subscription: dict,
        payload: dict,
        ttl: int,
        urgency: str,
        topic: str,
    ) -> ProviderResult: ...


def classify_status(status: int | None) -> ProviderResult:
    if status is not None and 200 <= status < 300:
        return ProviderResult(True, permanent=False, http_status=status)
    if status in (404, 410):
        return ProviderResult(
            False,
            permanent=True,
            expired=True,
            http_status=status,
            error_code="subscription_expired",
        )
    transient = status is None or status == 429 or (status is not None and status >= 500)
    return ProviderResult(
        False,
        permanent=not transient,
        http_status=status,
        error_code="network_error" if status is None else "push_service_error",
    )


def classify_exception(error: Exception) -> ProviderResult:
    status = getattr(getattr(error, "response", None), "status_code", None)
    if status is not None:
        return classify_status(status)
    if isinstance(error, RequestsTimeout):
        error_code = "timeout"
    elif isinstance(error, RequestsConnectionError):
        error_code = "connection_error"
    elif error.__class__.__module__.startswith("py_vapid"):
        error_code = "vapid_error"
    elif error.__class__.__module__.startswith("http_ece"):
        error_code = "encryption_error"
    else:
        error_code = "provider_error"
    return ProviderResult(False, permanent=False, error_code=error_code)


class PyWebPushProvider:
    def __init__(self, settings: PushSettings, send_impl: Callable | None = None):
        self.settings = settings
        if send_impl is None:
            from pywebpush import webpush

            send_impl = webpush
        self._send = send_impl

    def _vapid_private_key(self):
        value = self.settings.vapid_private_key.strip()
        if value.startswith("-----BEGIN ") and "PRIVATE KEY-----" in value:
            from py_vapid import Vapid

            return Vapid.from_pem(value.encode())
        return value

    def send(self, subscription: dict, payload: dict, ttl: int, urgency: str, topic: str) -> ProviderResult:
        try:
            vapid_private_key = self._vapid_private_key()
        except Exception:
            # PEM parsing failures are safe to identify by category only.
            return ProviderResult(False, permanent=False, error_code="vapid_error")
        try:
            response = self._send(
                subscription_info=subscription,
                data=json.dumps(payload, separators=(",", ":")),
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": self.settings.vapid_subject},
                ttl=ttl,
                headers={"Urgency": urgency, "Topic": topic},
                timeout=self.settings.request_timeout_seconds,
            )
            return classify_status(getattr(response, "status_code", None))
        except Exception as error:
            # Deliberately discard exception text: it can contain a capability URL.
            return classify_exception(error)
