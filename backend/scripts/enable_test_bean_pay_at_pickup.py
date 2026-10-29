"""One shop only: promote "Test Bean Café (TEST)" to live and turn on pay at pickup.

Approved by Marc for the private beta test. Safe to run more than once.
Scoped strictly to the slug below; refuses to touch anything else.

Run from the backend directory (DATABASE_URL already set on Canner):
    .venv/bin/python scripts/enable_test_bean_pay_at_pickup.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

TARGET_SLUG = "test-bean-cafe-test"


def run(session: Session, auth_settings, provider, *, slug: str = TARGET_SLUG) -> str:
    from app.jds_auth.models import Membership, Organization
    from app.payments.pay_at_pickup import get_order_settings, update_order_settings
    from app.platform.demo_service import DemoFunnelService

    if slug != TARGET_SLUG:
        raise SystemExit(f"Refusing: this script only handles {TARGET_SLUG}.")
    organization = session.scalar(select(Organization).where(Organization.slug == slug))
    if organization is None:
        raise SystemExit(f"No shop with slug {slug}; nothing changed.")
    owner_id = session.scalar(
        select(Membership.user_id)
        .where(Membership.organization_id == organization.id, Membership.status == "active")
        .order_by(Membership.created_at)
        .limit(1)
    )
    if organization.commercial_mode != "live":
        DemoFunnelService(session, auth_settings, provider).promote_to_live(
            organization_id=organization.id, actor_user_id=owner_id, now=datetime.now(timezone.utc)
        )
    current = get_order_settings(session, organization.id)
    update_order_settings(
        session,
        organization.id,
        pay_at_pickup_enabled=True,
        pay_at_pickup_min_completed_orders=0,  # test shop: allow the very first order
        pay_at_pickup_max_total_cents=max(current.pay_at_pickup_max_total_cents, 5000),
        new_order_alert_email=current.new_order_alert_email,
    )
    session.commit()
    result = get_order_settings(session, organization.id)
    return f"ok {slug}: mode=live pay_at_pickup={result.pay_at_pickup_enabled} max_cents={result.pay_at_pickup_max_total_cents}"


def main() -> None:
    from app.db.engine import create_database_engine
    from app.jds_auth.config import AuthSettings
    from app.jds_auth.provider import SupabaseIdentityProvider

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")
    settings = AuthSettings.from_env()
    engine = create_database_engine(database_url)
    try:
        with Session(engine) as session:
            print(run(session, settings, SupabaseIdentityProvider(settings)))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
