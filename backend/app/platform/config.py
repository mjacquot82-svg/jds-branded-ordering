from __future__ import annotations

import os

STANDARD_STOREFRONT_BASE_DOMAIN = "order.jdsstudio.ca"


def storefront_base_domain() -> str | None:
    value = os.getenv("JDS_STOREFRONT_BASE_DOMAIN", "").strip().lower().strip(".")
    return value or None


def hosted_storefront_hostname(slug: str) -> str | None:
    base = storefront_base_domain()
    return f"{slug}.{base}" if base else None


def standard_storefront_hostname(slug: str) -> str:
    """Product-facing JDS address; independent of environment routing and DNS."""
    return f"{slug}.{STANDARD_STOREFRONT_BASE_DOMAIN}"


def default_plan_key() -> str | None:
    value = os.getenv("JDS_DEFAULT_BILLING_PLAN_KEY", "").strip()
    return value or None


def storefront_url(hostname: str) -> str:
    scheme = os.getenv("JDS_STOREFRONT_SCHEME", "https").strip().lower()
    if scheme not in {"http", "https"}:
        scheme = "https"
    return f"{scheme}://{hostname}"


def storefront_request_host(request) -> str | None:
    """Host to resolve a storefront from.

    On Canner the web project proxies /api to the API project, so the API sees its own
    hostname in Host and the shop's hostname in X-Forwarded-Host. When
    JDS_TRUST_PROXY_STOREFRONT_HOST=true, a forwarded host that is exactly one label under
    JDS_STOREFRONT_BASE_DOMAIN (e.g. maple.order.jdsstudio.ca) is used instead. That only
    selects among verified, public-ready storefront mappings, which are public anyway.
    """
    own = request.headers.get("host") or request.url.hostname
    if os.getenv("JDS_TRUST_PROXY_STOREFRONT_HOST", "false").strip().lower() != "true":
        return own
    base = storefront_base_domain()
    forwarded = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip().split(":", 1)[0].rstrip(".").lower()
    if base and forwarded.endswith(f".{base}"):
        label = forwarded[: -len(base) - 1]
        if label and "." not in label:
            return forwarded
    return own
