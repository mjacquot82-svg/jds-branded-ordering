from __future__ import annotations

import os


def storefront_base_domain() -> str | None:
    value = os.getenv("JDS_STOREFRONT_BASE_DOMAIN", "").strip().lower().strip(".")
    return value or None


def hosted_storefront_hostname(slug: str) -> str | None:
    base = storefront_base_domain()
    return f"{slug}.{base}" if base else None


def default_plan_key() -> str | None:
    value = os.getenv("JDS_DEFAULT_BILLING_PLAN_KEY", "").strip()
    return value or None


def storefront_url(hostname: str) -> str:
    scheme = os.getenv("JDS_STOREFRONT_SCHEME", "https").strip().lower()
    if scheme not in {"http", "https"}:
        scheme = "https"
    return f"{scheme}://{hostname}"
