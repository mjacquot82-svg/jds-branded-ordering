"""One shop only: promote "Test Bean Café (TEST)" to live and turn on pay at pickup.

Approved by Marc for the private beta test. Safe to run more than once.
Scoped strictly to the owner email + slug + id below; refuses to touch anything else.

Run from the backend directory (DATABASE_URL already set on Canner):
    .venv/bin/python scripts/enable_test_bean_pay_at_pickup.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

# Read from the live API as the test owner on 2026-10-29 (demo slugs are generated).
TARGET_OWNER_EMAIL = "mjacquot82+jdstest2@gmail.com"
TARGET_SLUG = "test-bean-caf-test"
TARGET_ORGANIZATION_ID = "b541893d-f96b-48e2-ada8-4db6d19713b0"


def run(session: Session, auth_settings, provider) -> str:
    from app.jds_auth.models import JdsUser, Membership, Organization, Role
    from app.payments.pay_at_pickup import get_order_settings, update_order_settings
    from app.platform.demo_service import DemoFunnelService

    owner = session.scalar(select(JdsUser).where(func.lower(JdsUser.primary_email) == TARGET_OWNER_EMAIL.lower()))
    if owner is None:
        raise SystemExit(f"No user {TARGET_OWNER_EMAIL}; nothing changed.")
    organizations = session.scalars(
        select(Organization)
        .join(Membership, Membership.organization_id == Organization.id)
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.user_id == owner.id, Membership.status == "active", Role.key == "owner")
    ).all()
    if len(organizations) != 1:
        raise SystemExit(f"Refusing: {TARGET_OWNER_EMAIL} owns {len(organizations)} shops (expected exactly 1); nothing changed.")
    organization = organizations[0]
    if str(organization.id) != TARGET_ORGANIZATION_ID or organization.slug != TARGET_SLUG:
        raise SystemExit(f"Refusing: shop {organization.slug} does not match {TARGET_SLUG}; nothing changed.")
    owner_id = owner.id
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
    return f"ok {organization.slug}: mode=live pay_at_pickup={result.pay_at_pickup_enabled} max_cents={result.pay_at_pickup_max_total_cents}"


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
