"""Minimal Square REST client (httpx). Never logs tokens or response bodies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.square.config import SQUARE_API_VERSION, SQUARE_OAUTH_SCOPES, SquareSettings


class SquareApiError(RuntimeError):
    def __init__(self, message: str, *, code: str = "square_api_error", status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class SquareTokenPair:
    access_token: str
    refresh_token: str
    expires_at: datetime
    merchant_id: str


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise SquareApiError("Square returned no expiry.", code="square_invalid_response")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class SquareClient:
    def __init__(self, settings: SquareSettings, *, timeout: float = 15.0):
        self.settings = settings
        self.timeout = timeout

    def authorization_url(self, state: str) -> str:
        query = urlencode({
            "client_id": self.settings.application_id,
            "scope": " ".join(SQUARE_OAUTH_SCOPES),
            "session": "false",
            "state": state,
            "redirect_uri": self.settings.callback_url,
        })
        return f"{self.settings.api_base_url}/oauth2/authorize?{query}"

    def _request(self, method: str, path: str, *, token: str | None = None, json: dict | None = None) -> dict:
        headers = {"Square-Version": SQUARE_API_VERSION, "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = httpx.request(
                method, f"{self.settings.api_base_url}{path}", headers=headers, json=json, timeout=self.timeout
            )
        except httpx.HTTPError as error:
            raise SquareApiError("Square could not be reached.", code="square_unreachable") from error
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 400:
            code = "square_api_error"
            errors = data.get("errors") if isinstance(data, dict) else None
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                code = f"square_{str(errors[0].get('code') or 'error').lower()}"
            if response.status_code == 401:
                code = "square_unauthorized"
            raise SquareApiError("Square request failed.", code=code, status_code=response.status_code)
        if not isinstance(data, dict):
            raise SquareApiError("Square returned an invalid response.", code="square_invalid_response")
        return data

    def _token(self, payload: dict[str, str]) -> SquareTokenPair:
        data = self._request("POST", "/oauth2/token", json={
            "client_id": self.settings.application_id,
            "client_secret": self.settings.application_secret,
            **payload,
        })
        access = data.get("access_token")
        merchant = data.get("merchant_id")
        refresh = data.get("refresh_token") or payload.get("refresh_token")
        if not access or not merchant or not refresh:
            raise SquareApiError("Square returned an incomplete token.", code="square_invalid_response")
        return SquareTokenPair(
            access_token=str(access), refresh_token=str(refresh),
            expires_at=_parse_time(data.get("expires_at")), merchant_id=str(merchant),
        )

    def exchange_code(self, code: str) -> SquareTokenPair:
        return self._token({
            "grant_type": "authorization_code", "code": code, "redirect_uri": self.settings.callback_url,
        })

    def refresh_access_token(self, refresh_token: str) -> SquareTokenPair:
        return self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def list_locations(self, access_token: str) -> list[dict[str, Any]]:
        data = self._request("GET", "/v2/locations", token=access_token)
        locations = data.get("locations") or []
        return [loc for loc in locations if isinstance(loc, dict)]

    def create_payment_link(self, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", "/v2/online-checkout/payment-links", token=access_token, json=payload)
        link = data.get("payment_link")
        if not isinstance(link, dict) or not link.get("url") or not link.get("order_id"):
            raise SquareApiError("Square returned an invalid payment link.", code="square_invalid_response")
        return link

    def get_order(self, access_token: str, order_id: str) -> dict[str, Any]:
        data = self._request("GET", f"/v2/orders/{order_id}", token=access_token)
        order = data.get("order")
        if not isinstance(order, dict):
            raise SquareApiError("Square returned an invalid order.", code="square_invalid_response")
        return order

    def get_payment(self, access_token: str, payment_id: str) -> dict[str, Any]:
        data = self._request("GET", f"/v2/payments/{payment_id}", token=access_token)
        payment = data.get("payment")
        if not isinstance(payment, dict):
            raise SquareApiError("Square returned an invalid payment.", code="square_invalid_response")
        return payment

    def refund_payment(self, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", "/v2/refunds", token=access_token, json=payload)
        refund = data.get("refund")
        if not isinstance(refund, dict) or not refund.get("id"):
            raise SquareApiError("Square returned an invalid refund.", code="square_invalid_response")
        return refund
