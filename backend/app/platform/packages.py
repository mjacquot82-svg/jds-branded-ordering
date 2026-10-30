"""JDS packages shown in the /build picker. Record-only: nothing here bills or gates features."""

from __future__ import annotations

PACKAGE_KEYS = ("starter", "plus", "pro")

BETA_NOTICE = "Free during the beta — you won't be charged. We'll give you 30 days' notice before any charge."

PACKAGES = [
    {
        "key": "starter", "name": "Starter", "amountCents": 15000, "currency": "CAD", "interval": "month",
        "features": [
            {"label": "Your own branded app"},
            {"label": "Menu with options"},
            {"label": "Online ordering & card payment with pickup times"},
            {"label": "Order screen"},
            {"label": "Email receipts"},
            {"label": "Refunds"},
            {"label": "Marketing kit"},
        ],
    },
    {
        "key": "plus", "name": "Plus", "amountCents": 22500, "currency": "CAD", "interval": "month",
        "includes": "Everything in Starter, plus:",
        "features": [
            {"label": "Loyalty rewards"},
            {"label": "Announcements & push alerts"},
            {"label": "Customer list"},
            {"label": "Staff PIN logins"},
        ],
    },
    {
        "key": "pro", "name": "Pro", "amountCents": 30000, "currency": "CAD", "interval": "month",
        "includes": "Everything in Plus, plus:",
        "features": [
            {"label": "'Order ready' text alerts (300/month included)", "comingSoon": True},
            {"label": "Sales reports", "comingSoon": True},
            {"label": "Your own web address", "comingSoon": True},
            {"label": "Priority support"},
        ],
    },
]

NOTES = ["Extra locations: $75/month each", "Custom features: ask us"]


def package_catalog() -> dict:
    return {"packages": PACKAGES, "notes": NOTES, "betaNotice": BETA_NOTICE}


def package_name(key: str | None) -> str | None:
    return next((item["name"] for item in PACKAGES if item["key"] == key), None)
