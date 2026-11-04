from __future__ import annotations

import hmac
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


STOREFRONT_HOST_HEADER = "x-jds-storefront-host"
PROXY_SECRET_HEADER = "x-jds-proxy-secret"


def _single_label_storefront_host(value: str) -> str | None:
    base = storefront_base_domain()
    host = (value or "").split(",", 1)[0].strip().split(":", 1)[0].rstrip(".").lower()
    if base and host.endswith(f".{base}"):
        label = host[: -len(base) - 1]
        if label and "." not in label:
            return host
    return None


def storefront_request_host(request) -> str | None:
    """Host to resolve a storefront from.

    On Canner the web project proxies /api to the API project. Canner's edge in front of
    the API overwrites X-Forwarded-Host with the API's own hostname, so the shop hostname
    is lost. The web proxy therefore also sends X-JDS-Storefront-Host plus
    X-JDS-Proxy-Secret; when JDS_STOREFRONT_PROXY_SECRET is set and the secret matches
    (constant-time), that dedicated header is used. JDS_TRUST_PROXY_STOREFRONT_HOST=true
    keeps the older X-Forwarded-Host path. Either way only a host exactly one label under
    JDS_STOREFRONT_BASE_DOMAIN is accepted, and it only selects a live, public-ready shop.
    """
    own = request.headers.get("host") or request.url.hostname
    secret = os.getenv("JDS_STOREFRONT_PROXY_SECRET", "").strip()
    if secret:
        supplied = request.headers.get(PROXY_SECRET_HEADER, "")
        if supplied and hmac.compare_digest(supplied.encode(), secret.encode()):
            dedicated = _single_label_storefront_host(request.headers.get(STOREFRONT_HOST_HEADER, ""))
            if dedicated:
                return dedicated
    if os.getenv("JDS_TRUST_PROXY_STOREFRONT_HOST", "false").strip().lower() != "true":
        return own
    return _single_label_storefront_host(request.headers.get("x-forwarded-host", "")) or own
