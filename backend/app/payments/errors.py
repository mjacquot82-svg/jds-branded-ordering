"""Stable payment-port errors (no secrets in messages)."""

from __future__ import annotations


class PaymentPortError(Exception):
    """Base payment-port failure."""

    code: str = "payment_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class ProviderNotConfiguredError(PaymentPortError):
    code = "payment_provider_not_configured"


class UnsupportedProviderError(PaymentPortError):
    code = "payment_provider_unsupported"


class ProviderNotConnectedError(PaymentPortError):
    code = "payment_provider_not_connected"


class PaymentCheckoutError(PaymentPortError):
    code = "payment_checkout_failed"
