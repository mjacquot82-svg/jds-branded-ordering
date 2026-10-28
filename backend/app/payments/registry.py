"""Provider registry. Adding Square/Stripe/Moneris = register adapter only."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.payments.errors import UnsupportedProviderError
from app.payments.models import ENABLED_PROVIDER_KEYS, KNOWN_PROVIDER_KEYS

if TYPE_CHECKING:
    from app.payments.port import PaymentProvider

SUPPORTED_PROVIDERS = frozenset(ENABLED_PROVIDER_KEYS)


def get_provider(provider_key: str) -> PaymentProvider:
    key = (provider_key or "").strip().lower()
    if key not in KNOWN_PROVIDER_KEYS:
        raise UnsupportedProviderError(
            f"Unknown payment provider '{key or '(empty)'}'.",
            code="payment_provider_unknown",
        )
    if key not in ENABLED_PROVIDER_KEYS:
        raise UnsupportedProviderError(
            f"Payment provider '{key}' is not enabled on this platform.",
            code="payment_provider_unsupported",
        )
    if key == "clover":
        from app.payments.adapters.clover_adapter import CloverPaymentProvider

        return CloverPaymentProvider()
    raise UnsupportedProviderError(
        f"Payment provider '{key}' is not enabled on this platform.",
        code="payment_provider_unsupported",
    )


def resolve_provider_key(provider_key: str | None) -> str:
    key = (provider_key or "").strip().lower()
    if not key:
        raise UnsupportedProviderError(
            "No payment provider is configured for this business.",
            code="payment_provider_not_configured",
        )
    # Force registry validation (fail closed; no silent Clover fallback).
    get_provider(key)
    return key
