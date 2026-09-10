"""Server-enforced free-prospect demo limits (M2).

Generous enough to build a convincing café demo; tight enough to bound storage
and abuse cost. Live merchants are not constrained by these caps.
"""
from __future__ import annotations

import os

# Catalog
DEMO_MAX_PRODUCTS = 25
DEMO_MAX_CATEGORIES = 8

# Media (tenant uploads only; starter references do not count)
DEMO_MAX_MEDIA_FILES = 20
DEMO_MAX_STORAGE_BYTES = 25 * 1024 * 1024  # 25 MiB total active media
DEMO_ALLOWED_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
# Reuse platform image bounds; product images still require >= 800×800.
DEMO_MAX_IMAGE_WIDTH = 12_000
DEMO_MAX_IMAGE_HEIGHT = 12_000
DEMO_MAX_IMAGE_BYTES = 5_000_000  # per-file cap inside the platform 10 MB ceiling

# Funnel / abuse (in addition to auth rate limits)
DEMO_SIGNUP_IP_MAX = 8
DEMO_SIGNUP_IP_WINDOW_SECONDS = 60 * 60
DEMO_ACTIVATION_REQUEST_MAX = 3
DEMO_ACTIVATION_REQUEST_WINDOW_SECONDS = 24 * 60 * 60
DEMO_FUNNEL_EVENT_MAX = 120
DEMO_FUNNEL_EVENT_WINDOW_SECONDS = 60 * 60

# Retention policy (documented; auto-delete is NOT enabled in M2)
DEMO_RETENTION_INACTIVE_DAYS = 90
DEMO_RETENTION_AUTO_DELETE_ENABLED = False

STANDARD_PLAN_KEY = "jds-standard"
DEMO_PLAN_KEY = "jds-demo"
DEFAULT_STANDARD_AMOUNT_CENTS = 15_000  # C$150.00
DEFAULT_CURRENCY = "CAD"


def standard_plan_amount_cents() -> int:
    raw = os.getenv("JDS_STANDARD_PLAN_MONTHLY_CENTS", "").strip()
    if raw.isdigit():
        return int(raw)
    # Allow dollars-style env for operators.
    dollars = os.getenv("JDS_STANDARD_PLAN_MONTHLY_CAD", "").strip()
    if dollars:
        try:
            return int(round(float(dollars) * 100))
        except ValueError:
            pass
    return DEFAULT_STANDARD_AMOUNT_CENTS


def limits_payload() -> dict:
    return {
        "maxProducts": DEMO_MAX_PRODUCTS,
        "maxCategories": DEMO_MAX_CATEGORIES,
        "maxMediaFiles": DEMO_MAX_MEDIA_FILES,
        "maxStorageBytes": DEMO_MAX_STORAGE_BYTES,
        "maxImageBytes": DEMO_MAX_IMAGE_BYTES,
        "allowedMediaTypes": sorted(DEMO_ALLOWED_MEDIA_TYPES),
        "maxImageWidth": DEMO_MAX_IMAGE_WIDTH,
        "maxImageHeight": DEMO_MAX_IMAGE_HEIGHT,
        "retentionInactiveDays": DEMO_RETENTION_INACTIVE_DAYS,
        "retentionAutoDeleteEnabled": DEMO_RETENTION_AUTO_DELETE_ENABLED,
    }
