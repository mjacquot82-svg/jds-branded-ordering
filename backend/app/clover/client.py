import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from app.clover.config import CloverSettings


class CloverApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "clover_api_error",
        upstream_status: int | None = None,
        upstream_error_code: str | None = None,
        upstream_error_message: str | None = None,
        upstream_response_body: object | None = None,
        upstream_response_headers: dict[str, str] | None = None,
        timeout_information: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.upstream_status = upstream_status
        self.upstream_error_code = upstream_error_code
        self.upstream_error_message = upstream_error_message
        self.upstream_response_body = upstream_response_body
        self.upstream_response_headers = upstream_response_headers or {}
        self.timeout_information = timeout_information


MAX_DIAGNOSTIC_BODY_CHARACTERS = 4096
DIAGNOSTIC_RESPONSE_HEADERS = frozenset(
    {
        "cf-ray",
        "content-type",
        "date",
        "retry-after",
        "trace-id",
        "x-correlation-id",
        "x-request-id",
        "x-trace-id",
    }
)
SENSITIVE_RESPONSE_KEYS = frozenset(
    {
        "access_token",
        "authorization",
        "card",
        "cardnumber",
        "customer",
        "email",
        "firstname",
        "lastname",
        "merchant_private_token",
        "paymentmethod",
        "phonenumber",
        "refresh_token",
        "source",
        "token",
    }
)
NORMALIZED_SENSITIVE_RESPONSE_KEYS = frozenset(
    key.replace("_", "") for key in SENSITIVE_RESPONSE_KEYS
)
SENSITIVE_RESPONSE_KEY_FRAGMENTS = (
    "authorization",
    "card",
    "customer",
    "email",
    "firstname",
    "lastname",
    "paymentmethod",
    "phone",
    "secret",
    "source",
    "token",
)


def _is_sensitive_response_key(key: object) -> bool:
    normalized = str(key).replace("-", "").replace("_", "").lower()
    return normalized in NORMALIZED_SENSITIVE_RESPONSE_KEYS or any(
        fragment in normalized for fragment in SENSITIVE_RESPONSE_KEY_FRAGMENTS
    )


def _sanitize_response_body(
    value: object,
    sensitive_values: set[str] | None = None,
) -> object:
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if _is_sensitive_response_key(key)
                else _sanitize_response_body(item, sensitive_values)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_response_body(item, sensitive_values) for item in value]
    if isinstance(value, str):
        sanitized = _sanitize_diagnostic_text(value, sensitive_values)
        if len(sanitized) > MAX_DIAGNOSTIC_BODY_CHARACTERS:
            return sanitized[:MAX_DIAGNOSTIC_BODY_CHARACTERS] + "...[truncated]"
        return sanitized
    return value


def _sensitive_values(value: object, *, sensitive: bool = False) -> set[str]:
    values: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            values.update(
                _sensitive_values(item, sensitive=sensitive or _is_sensitive_response_key(key))
            )
    elif isinstance(value, list):
        for item in value:
            values.update(_sensitive_values(item, sensitive=sensitive))
    elif sensitive and isinstance(value, (str, int, float)):
        rendered = str(value)
        if rendered:
            values.add(rendered)
    return values


def _sanitize_diagnostic_text(
    value: str,
    sensitive_values: set[str] | None = None,
) -> str:
    sanitized = value
    for sensitive_value in sorted(sensitive_values or (), key=len, reverse=True):
        sanitized = sanitized.replace(sensitive_value, "[REDACTED]")
    patterns = (
        (r"(?i)bearer\s+[a-z0-9._~+/=-]+", "Bearer [REDACTED]"),
        (r"(?i)\b[\w.!#$%&'*+/=?^`{|}~-]+@[\w.-]+\.[a-z]{2,}\b", "[REDACTED_EMAIL]"),
        (r"(?<!\d)(?:\+?\d[\d ().-]{7,}\d)(?!\d)", "[REDACTED_NUMBER]"),
    )
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized)
    return sanitized


def _bounded_response_body(value: object) -> object:
    sanitized = _sanitize_response_body(value, _sensitive_values(value))
    serialized = json.dumps(sanitized, default=str, separators=(",", ":"))
    if len(serialized) <= MAX_DIAGNOSTIC_BODY_CHARACTERS:
        return sanitized
    return serialized[:MAX_DIAGNOSTIC_BODY_CHARACTERS] + "...[truncated]"


def _diagnostic_headers(response: httpx.Response) -> dict[str, str]:
    return {
        name.lower(): value
        for name, value in response.headers.items()
        if name.lower() in DIAGNOSTIC_RESPONSE_HEADERS
    }


def _error_value(data: object, *keys: str) -> str | None:
    if not isinstance(data, dict):
        return None
    sensitive_values = _sensitive_values(data)
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return _sanitize_diagnostic_text(value, sensitive_values)[:1000]
    detail = data.get("detail")
    if isinstance(detail, dict):
        return _error_value(detail, *keys)
    return None


@dataclass(frozen=True)
class CloverTokenPair:
    access_token: str
    refresh_token: str
    expires_at: datetime
    refresh_expires_at: datetime


class CloverClient:
    def __init__(
        self,
        settings: CloverSettings,
        *,
        http_client: httpx.Client | None = None,
    ):
        self.settings = settings
        self.http_client = http_client

    def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        try:
            if self.http_client is not None:
                return self.http_client.post(url, **kwargs)
            timeout = httpx.Timeout(15, connect=5)
            with httpx.Client(timeout=timeout) as client:
                return client.post(url, **kwargs)
        except httpx.TimeoutException as error:
            try:
                request = error.request
            except RuntimeError:
                request = None
            raise CloverApiError(
                "Clover request timed out.",
                code="clover_timeout",
                timeout_information={
                    "exception_type": type(error).__name__,
                    "method": request.method if request else None,
                    "phase": type(error).__name__.removesuffix("Timeout").lower(),
                    "production_timeout_seconds": {
                        "connect": 5,
                        "pool": 15,
                        "read": 15,
                        "write": 15,
                    },
                    "url_host": request.url.host if request else None,
                    "url_path": request.url.path if request else None,
                },
            ) from error
        except httpx.RequestError as error:
            raise CloverApiError(
                "Unable to reach Clover.", code="clover_unreachable"
            ) from error

    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        try:
            if self.http_client is not None:
                return self.http_client.get(url, **kwargs)
            timeout = httpx.Timeout(15, connect=5)
            with httpx.Client(timeout=timeout) as client:
                return client.get(url, **kwargs)
        except httpx.TimeoutException as error:
            try:
                request = error.request
            except RuntimeError:
                request = None
            raise CloverApiError(
                "Clover request timed out.",
                code="clover_timeout",
                timeout_information={
                    "exception_type": type(error).__name__,
                    "method": request.method if request else None,
                    "phase": type(error).__name__.removesuffix("Timeout").lower(),
                    "production_timeout_seconds": {
                        "connect": 5,
                        "pool": 15,
                        "read": 15,
                        "write": 15,
                    },
                    "url_host": request.url.host if request else None,
                    "url_path": request.url.path if request else None,
                },
            ) from error
        except httpx.RequestError as error:
            raise CloverApiError(
                "Unable to reach Clover.", code="clover_unreachable"
            ) from error

    def authorization_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": self.settings.app_id,
                "redirect_uri": self.settings.callback_url,
                "response_type": "code",
                "state": state,
            }
        )
        return f"{self.settings.authorize_base_url}/oauth/v2/authorize?{query}"

    def exchange_code(self, code: str) -> CloverTokenPair:
        return self._token_request(
            "/oauth/v2/token",
            {
                "client_id": self.settings.app_id,
                "client_secret": self.settings.app_secret,
                "code": code,
            },
        )

    def refresh_access_token(self, refresh_token: str) -> CloverTokenPair:
        return self._token_request(
            "/oauth/v2/refresh",
            {
                "client_id": self.settings.app_id,
                "refresh_token": refresh_token,
            },
        )

    def _token_request(self, path: str, payload: dict[str, str]) -> CloverTokenPair:
        response = self._post(
            f"{self.settings.api_base_url}{path}",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=payload,
        )
        data = self._response_json(response, "Clover token request failed")
        try:
            expires_at = datetime.fromtimestamp(
                int(data["access_token_expiration"]), tz=timezone.utc
            )
            refresh_expires_at = datetime.fromtimestamp(
                int(data["refresh_token_expiration"]), tz=timezone.utc
            )
            if expires_at <= datetime.now(timezone.utc):
                raise ValueError("access token is already expired")
            if refresh_expires_at <= expires_at:
                raise ValueError("refresh token must outlive the access token")
            access_token = data["access_token"]
            refresh_token = data["refresh_token"]
            if (
                not isinstance(access_token, str)
                or not access_token
                or not isinstance(refresh_token, str)
                or not refresh_token
            ):
                raise ValueError("tokens must be non-empty strings")
            return CloverTokenPair(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                refresh_expires_at=refresh_expires_at,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CloverApiError("Clover returned an invalid token response.") from error

    def create_checkout(
        self,
        *,
        access_token: str,
        merchant_id: str,
        payload: dict,
    ) -> dict:
        response = self._post(
            (
                f"{self.settings.hosted_checkout_base_url}"
                "/invoicingcheckoutservice/v1/checkouts"
            ),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": "guesthouse-preorder/0.1",
                "X-Clover-Merchant-Id": merchant_id,
            },
            json=payload,
        )
        data = self._response_json(response, "Clover checkout request failed")
        href = data.get("href")
        checkout_session_id = data.get("checkoutSessionId")
        if (
            not isinstance(href, str)
            or not href
            or urlparse(href).scheme != "https"
            or not urlparse(href).hostname
            or not isinstance(checkout_session_id, str)
            or not checkout_session_id
        ):
            raise CloverApiError(
                "Clover returned an invalid checkout response.",
                code="clover_invalid_response",
                upstream_status=response.status_code,
                upstream_response_body=_bounded_response_body(data),
                upstream_response_headers=_diagnostic_headers(response),
            )
        return data

    def get_payment(
        self,
        *,
        access_token: str,
        merchant_id: str,
        payment_id: str,
    ) -> dict:
        response = self._get(
            (
                f"{self.settings.platform_api_base_url}/v3/merchants/"
                f"{merchant_id}/payments/{payment_id}"
            ),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "guesthouse-preorder/0.1",
            },
        )
        return self._response_json(response, "Clover payment lookup failed")

    def get_merchant_tax_rates(
        self,
        *,
        access_token: str,
        merchant_id: str,
    ) -> tuple[dict, int, dict[str, str]]:
        """Temporary diagnostic read of the merchant's configured tax rates."""
        response = self._get(
            (
                f"{self.settings.api_base_url}/v3/merchants/"
                f"{merchant_id}/tax_rates"
            ),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "guesthouse-preorder/0.1",
            },
        )
        data = self._response_json(response, "Clover tax rates request failed")
        return data, response.status_code, _diagnostic_headers(response)

    @staticmethod
    def _response_json(response: httpx.Response, message: str) -> dict:
        try:
            data = response.json()
        except ValueError as error:
            raise CloverApiError(
                f"{message}: invalid response.",
                code="clover_invalid_response",
                upstream_status=response.status_code,
                upstream_response_body={
                    "body": "[NON_JSON_RESPONSE_OMITTED]",
                    "character_count": len(response.text),
                },
                upstream_response_headers=_diagnostic_headers(response),
            ) from error
        if not response.is_success:
            raise CloverApiError(
                f"{message} ({response.status_code}).",
                code="clover_rejected_request",
                upstream_status=response.status_code,
                upstream_error_code=_error_value(data, "code", "error", "errorCode"),
                upstream_error_message=_error_value(
                    data, "message", "error_description", "errorMessage"
                ),
                upstream_response_body=_bounded_response_body(data),
                upstream_response_headers=_diagnostic_headers(response),
            )
        if not isinstance(data, dict):
            raise CloverApiError(
                f"{message}: invalid response.",
                code="clover_invalid_response",
                upstream_status=response.status_code,
            )
        return data
