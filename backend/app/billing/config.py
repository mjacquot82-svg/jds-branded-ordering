"""Billing settings. Everything is OFF unless JDS_BILLING_ENABLED is true.

JDS_BILLING_ENABLED                  master switch (default false): charging, reminders, pausing, feature gating
JDS_BILLING_SQUARE_ENVIRONMENT       sandbox (default) | production
JDS_BILLING_SQUARE_ACCESS_TOKEN      secret: access token of JDS's OWN Square account (not a shop's)
JDS_BILLING_SQUARE_APPLICATION_ID    public: app id for the card form (Web Payments SDK)
JDS_BILLING_SQUARE_LOCATION_ID       JDS's own Square location id
JDS_BILLING_PLAN_VARIATION_STARTER   Square subscription plan variation id for Starter
JDS_BILLING_PLAN_VARIATION_PLUS      ... for Plus
JDS_BILLING_PLAN_VARIATION_PRO       ... for Pro
JDS_BILLING_WEBHOOK_SIGNATURE_KEY    secret: signature key of the billing webhook subscription
JDS_BILLING_WEBHOOK_URL              exact public URL Square posts to (…/api/v1/billing/square/webhook)
JDS_BILLING_GRACE_DAYS               days after a failed charge before ordering pauses (default 7)
JDS_BILLING_EXTRA_LOCATION_CENTS     price per extra location (default 7500)
JDS_COCKPIT_FEED_TOKEN               secret: bearer token for the read-only Cockpit feed (feed disabled if unset)
JDS_COCKPIT_WEBHOOK_URL              optional: Cockpit URL to POST payment events to (off if unset)
"""

from __future__ import annotations

import os
from dataclasses import dataclass

PACKAGE_PRICES_CENTS = {"starter": 15000, "plus": 22500, "pro": 30000}


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def billing_enabled() -> bool:
    return _flag("JDS_BILLING_ENABLED")


def grace_days() -> int:
    try:
        return max(1, int(os.getenv("JDS_BILLING_GRACE_DAYS", "7")))
    except ValueError:
        return 7


def extra_location_cents() -> int:
    try:
        return max(0, int(os.getenv("JDS_BILLING_EXTRA_LOCATION_CENTS", "7500")))
    except ValueError:
        return 7500


def monthly_amount_cents(package_key: str, extra_locations: int = 0) -> int:
    return PACKAGE_PRICES_CENTS[package_key] + max(0, extra_locations) * extra_location_cents()


@dataclass(frozen=True)
class BillingSquareSettings:
    environment: str
    access_token: str
    application_id: str
    location_id: str
    plan_variations: dict
    webhook_signature_key: str
    webhook_url: str

    @classmethod
    def from_env(cls) -> "BillingSquareSettings":
        return cls(
            environment=(os.getenv("JDS_BILLING_SQUARE_ENVIRONMENT", "sandbox").strip().lower() or "sandbox"),
            access_token=os.getenv("JDS_BILLING_SQUARE_ACCESS_TOKEN", "").strip(),
            application_id=os.getenv("JDS_BILLING_SQUARE_APPLICATION_ID", "").strip(),
            location_id=os.getenv("JDS_BILLING_SQUARE_LOCATION_ID", "").strip(),
            plan_variations={key: os.getenv(f"JDS_BILLING_PLAN_VARIATION_{key.upper()}", "").strip() for key in PACKAGE_PRICES_CENTS},
            webhook_signature_key=os.getenv("JDS_BILLING_WEBHOOK_SIGNATURE_KEY", "").strip(),
            webhook_url=os.getenv("JDS_BILLING_WEBHOOK_URL", "").strip(),
        )

    @property
    def api_base_url(self) -> str:
        return "https://connect.squareup.com" if self.environment == "production" else "https://connect.squareupsandbox.com"

    @property
    def web_sdk_url(self) -> str:
        return "https://web.squarecdn.com/v1/square.js" if self.environment == "production" else "https://sandbox.web.squarecdn.com/v1/square.js"

    def is_configured(self) -> bool:
        return bool(self.access_token and self.application_id and self.location_id and all(self.plan_variations.values()))
