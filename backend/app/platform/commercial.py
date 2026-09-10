"""Commercial mode helpers: FREE PROSPECT vs PAYING LIVE MERCHANT (M2)."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.jds_auth.models import Organization

COMMERCIAL_PROSPECT = "prospect"
COMMERCIAL_LIVE = "live"
VALID_COMMERCIAL_MODES = frozenset({COMMERCIAL_PROSPECT, COMMERCIAL_LIVE})


def _read_mode(session: Session, organization_id: UUID) -> str:
    """Read commercial_mode without leaving the caller's session transaction open.

    Order/payment services call ``session.begin()`` and fail if the request
    session already autobegan from an earlier ``get()``. Use a side Session on
    the same bind for the authoritative read.
    """
    bind = session.get_bind()
    with Session(bind) as side:
        organization = side.get(Organization, organization_id)
        if organization is None:
            return COMMERCIAL_LIVE
        mode = getattr(organization, "commercial_mode", None) or COMMERCIAL_LIVE
        return mode if mode in VALID_COMMERCIAL_MODES else COMMERCIAL_LIVE


def organization_commercial_mode(session: Session, organization_id: UUID) -> str:
    return _read_mode(session, organization_id)


def is_prospect(session: Session, organization_id: UUID) -> bool:
    return organization_commercial_mode(session, organization_id) == COMMERCIAL_PROSPECT


def is_live(session: Session, organization_id: UUID) -> bool:
    return organization_commercial_mode(session, organization_id) == COMMERCIAL_LIVE


def enforce_live_commerce(session: Session, organization_id: UUID, *, action: str = "commerce") -> None:
    """Fail closed: prospects cannot accept real orders/payments or self-upgrade."""
    if is_prospect(session, organization_id):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "demo_commerce_locked",
                "message": (
                    "This store is a free demo. Real orders and payments stay locked "
                    "until JDS activates your live plan."
                ),
                "action": action,
                "commercialMode": COMMERCIAL_PROSPECT,
            },
        )


def enforce_not_self_upgrade(session: Session, organization_id: UUID) -> None:
    """Prospects cannot flip commercial_mode or lifecycle to live via request tampering."""
    if is_prospect(session, organization_id):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "demo_activation_required",
                "message": "Request activation to go live. Self-upgrade is not available.",
                "commercialMode": COMMERCIAL_PROSPECT,
            },
        )
