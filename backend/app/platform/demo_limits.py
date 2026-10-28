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

# Funnel / abuse (M2.5 controlled pilot — tighter than open ads)
# ~5–10 invitees: keep signup/tenant creation scarce per IP/email.
DEMO_SIGNUP_IP_MAX = 5
DEMO_SIGNUP_IP_WINDOW_SECONDS = 60 * 60
DEMO_SIGNUP_EMAIL_MAX = 3
DEMO_SIGNUP_EMAIL_WINDOW_SECONDS = 24 * 60 * 60
DEMO_ENTER_IP_MAX = 15
DEMO_ENTER_IP_WINDOW_SECONDS = 60 * 60
DEMO_TENANT_CREATE_IP_MAX = 5
DEMO_TENANT_CREATE_IP_WINDOW_SECONDS = 24 * 60 * 60
DEMO_UPLOAD_ORG_MAX = 30
DEMO_UPLOAD_ORG_WINDOW_SECONDS = 60 * 60
DEMO_ACTIVATION_REQUEST_MAX = 3
DEMO_ACTIVATION_REQUEST_WINDOW_SECONDS = 24 * 60 * 60
DEMO_FUNNEL_EVENT_MAX = 120
DEMO_FUNNEL_EVENT_WINDOW_SECONDS = 60 * 60
DEMO_RESEND_VERIFICATION_IP_MAX = 8
DEMO_RESEND_VERIFICATION_IP_WINDOW_SECONDS = 60 * 60
DEMO_RESEND_VERIFICATION_EMAIL_MAX = 3
DEMO_RESEND_VERIFICATION_EMAIL_WINDOW_SECONDS = 60 * 60

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



def demo_invite_code_required() -> bool:
    """When set, signup must supply matching invite code (controlled pilot)."""
    return bool(os.getenv("JDS_DEMO_INVITE_CODE", "").strip())


def demo_invite_code() -> str:
    return os.getenv("JDS_DEMO_INVITE_CODE", "").strip()


def captcha_configured() -> bool:
    """True only when Marc has supplied a vendor site+secret key (optional)."""
    provider = os.getenv("JDS_DEMO_CAPTCHA_PROVIDER", "").strip().lower()
    site = os.getenv("JDS_DEMO_CAPTCHA_SITE_KEY", "").strip()
    secret = os.getenv("JDS_DEMO_CAPTCHA_SECRET_KEY", "").strip()
    return provider in {"turnstile", "hcaptcha", "recaptcha"} and bool(site and secret)


def captcha_public_config() -> dict:
    if not captcha_configured():
        return {"enabled": False, "provider": None, "siteKey": None}
    return {
        "enabled": True,
        "provider": os.getenv("JDS_DEMO_CAPTCHA_PROVIDER", "").strip().lower(),
        "siteKey": os.getenv("JDS_DEMO_CAPTCHA_SITE_KEY", "").strip(),
    }


def pilot_config_payload() -> dict:
    return {
        "inviteRequired": demo_invite_code_required(),
        "captcha": captcha_public_config(),
        "noCreditCardToBuild": True,
        "goLiveApproxCad": standard_plan_amount_cents() / 100,
        "jdsSalesTakePercent": 0,
        "limits": limits_payload(),
    }

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
