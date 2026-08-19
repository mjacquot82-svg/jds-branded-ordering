from decimal import Decimal, ROUND_HALF_UP


TAX_RATE_SCALE = 10_000_000
DEFAULT_TAX_NAME = "HST"
DEFAULT_TAX_RATE_MILLIONTHS = 1_300_000


def calculate_tax_cents(subtotal_cents: int, tax_rate_millionths: int) -> int:
    if subtotal_cents < 0:
        raise ValueError("subtotal_cents must be nonnegative.")
    if not 0 <= tax_rate_millionths <= TAX_RATE_SCALE:
        raise ValueError("tax_rate_millionths is invalid.")
    return int(
        (Decimal(subtotal_cents) * Decimal(tax_rate_millionths) / TAX_RATE_SCALE)
        .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
