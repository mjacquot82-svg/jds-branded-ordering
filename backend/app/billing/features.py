"""Which features each package unlocks. Only enforced when billing is switched on."""

from __future__ import annotations

BASE = {"designStudio": True}
STARTER = dict(BASE)
PLUS = {**STARTER, "loyalty": True, "notifications": True, "customerList": True, "staffPins": True}
PRO = {**PLUS, "texts": True, "reports": True, "ownDomain": True, "prioritySupport": True}
ALL_FEATURES = dict(PRO)

PACKAGE_FEATURES = {"starter": STARTER, "plus": PLUS, "pro": PRO}

# Smallest package that includes a feature, for friendly "upgrade to ..." messages.
FEATURE_PACKAGE = {feature: next(key for key in ("starter", "plus", "pro") if PACKAGE_FEATURES[key].get(feature))
                   for feature in ALL_FEATURES}


def features_for(package_key: str | None) -> dict:
    return dict(PACKAGE_FEATURES.get(package_key or "starter", STARTER))
