"""Human order numbers like TBC-000123, with a prefix per shop."""

from __future__ import annotations

import re
import unicodedata

LEGACY_PREFIX = "GH"
FALLBACK_PREFIX = "JDS"
_IGNORED_WORDS = {"the", "and", "of", "a", "an"}


def order_reference_prefix(name: str | None, slug: str | None = None) -> str:
    """Initials of the shop name, up to 3 letters: "Test Bean Café (TEST)" -> "TBC"."""
    for source in (name, (slug or "").replace("-", " ")):
        text = unicodedata.normalize("NFKD", source or "").encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"['\u2019]", "", text)
        words = re.findall(r"[A-Za-z0-9]+", text)
        kept = [word for word in words if word.lower() not in _IGNORED_WORDS] or words
        if len(kept) == 1:
            prefix = kept[0][:3]
        else:
            prefix = "".join(word[0] for word in kept[:3])
        prefix = prefix.upper()
        if len(prefix) >= 2:
            return prefix
    return FALLBACK_PREFIX


def order_reference(order) -> str:
    return f"{getattr(order, 'reference_prefix', None) or LEGACY_PREFIX}-{order.id:06d}"
