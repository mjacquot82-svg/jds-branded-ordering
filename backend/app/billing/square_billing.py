"""Square Customers/Cards/Subscriptions calls against JDS's OWN Square account.

Never logs tokens, card data or response bodies. Tests swap `client_factory`.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from app.billing.config import BillingSquareSettings
from app.square.config import SQUARE_API_VERSION


class BillingSquareError(RuntimeError):
    def __init__(self, message: str, *, code: str = "square_billing_error"):
        super().__init__(message)
        self.code = code


class BillingSquareClient:
    def __init__(self, settings: BillingSquareSettings, *, timeout: float = 15.0):
        self.settings = settings
        self.timeout = timeout

    def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        try:
            response = httpx.request(
                method, f"{self.settings.api_base_url}{path}", json=json, timeout=self.timeout,
                headers={"Square-Version": SQUARE_API_VERSION, "Content-Type": "application/json",
                         "Authorization": f"Bearer {self.settings.access_token}"},
            )
        except httpx.HTTPError as error:
            raise BillingSquareError("Square could not be reached.", code="square_unreachable") from error
        if response.status_code >= 400:
            code = "square_rejected"
            try:
                errors = response.json().get("errors") or []
                if errors and errors[0].get("code"):
                    code = str(errors[0]["code"]).lower()
            except ValueError:
                pass
            raise BillingSquareError("Square declined the request.", code=code)
        return response.json()

    def create_customer(self, *, email: str, name: str, reference_id: str, idempotency_key: str) -> str:
        data = self._request("POST", "/v2/customers", {"idempotency_key": idempotency_key, "email_address": email,
                                                       "company_name": name[:60], "reference_id": reference_id})
        return data["customer"]["id"]

    def create_card(self, *, source_id: str, customer_id: str, idempotency_key: str) -> dict:
        data = self._request("POST", "/v2/cards", {"idempotency_key": idempotency_key, "source_id": source_id,
                                                   "card": {"customer_id": customer_id}})
        return data["card"]

    def create_subscription(self, *, customer_id: str, card_id: str, plan_variation_id: str, amount_cents: int,
                            currency: str, idempotency_key: str) -> dict:
        data = self._request("POST", "/v2/subscriptions", {
            "idempotency_key": idempotency_key, "location_id": self.settings.location_id,
            "plan_variation_id": plan_variation_id, "customer_id": customer_id, "card_id": card_id,
            "price_override_money": {"amount": amount_cents, "currency": currency},
        })
        return data["subscription"]

    def update_subscription(self, subscription_id: str, *, card_id: str | None = None, amount_cents: int | None = None,
                            currency: str = "CAD") -> dict:
        body: dict = {}
        if card_id:
            body["card_id"] = card_id
        if amount_cents is not None:
            body["price_override_money"] = {"amount": amount_cents, "currency": currency}
        return self._request("PUT", f"/v2/subscriptions/{subscription_id}", {"subscription": body})["subscription"]

    def swap_plan(self, subscription_id: str, *, plan_variation_id: str) -> dict:
        """Square applies a plan swap at the start of the next billing period."""
        return self._request("POST", f"/v2/subscriptions/{subscription_id}/swap-plan",
                             {"new_plan_variation_id": plan_variation_id})


client_factory: Callable[[BillingSquareSettings], BillingSquareClient] = BillingSquareClient
