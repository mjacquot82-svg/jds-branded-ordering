"""Beta-only "shop links": https://<web>/?shop=<slug> instead of <slug>.order.jdsstudio.ca.

Off unless JDS_PILOT_SHOP_LINKS=true and JDS_ENVIRONMENT is not production. A shop link
only opens a storefront that is live and passes every public readiness check, i.e. the
same storefront anyone could open on its verified hostname. No DNS is needed.
"""

from __future__ import annotations

import os
import re
from contextvars import ContextVar

PILOT_SHOP_QUERY_KEY = "shop"
PILOT_SHOP_COOKIE = "__Host-jds_pilot_shop"
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
current_pilot_shop: ContextVar[str | None] = ContextVar("current_pilot_shop", default=None)


def pilot_shop_links_enabled() -> bool:
    return (
        os.getenv("JDS_PILOT_SHOP_LINKS", "false").strip().lower() == "true"
        and os.getenv("JDS_ENVIRONMENT", "").strip().lower() != "production"
    )


def valid_pilot_slug(value: str | None) -> str | None:
    slug = (value or "").strip().lower()
    return slug if 3 <= len(slug) <= 63 and _SLUG.fullmatch(slug) else None


def pilot_shop_url(slug: str) -> str | None:
    if not pilot_shop_links_enabled():
        return None
    frontend = os.getenv("FRONTEND_URL", "").rstrip("/")
    return f"{frontend}/?{PILOT_SHOP_QUERY_KEY}={slug}" if frontend else None
