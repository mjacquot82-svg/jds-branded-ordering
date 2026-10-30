"""Platform billing: card on file, monthly Square subscription, failed-payment grace, pausing.

Nothing here charges anyone unless JDS_BILLING_ENABLED=true AND Square billing settings are set.
Shops with organizations.billing_exempt=true (all beta shops) are never charged, gated or paused.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing import square_billing
from app.billing.config import BillingSquareSettings, billing_enabled, grace_days, monthly_amount_cents
from app.billing.features import ALL_FEATURES, FEATURE_PACKAGE, features_for
from app.billing.models import BillingPayment, ShopBillingAccount
from app.billing.usage import period_of, record_usage
from app.jds_auth.models import JdsUser, Membership, Organization, Role
from app.platform.models import OperationalAuditEvent
from app.platform.packages import package_name

logger = logging.getLogger(__name__)

REMINDER_EVERY = timedelta(days=2)
MAX_REMINDERS = 4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(session: Session, organization_id: UUID, action: str, actor: UUID | None = None, **metadata) -> None:
    session.add(OperationalAuditEvent(organization_id=organization_id, scope="tenant", actor_user_id=actor, action=action,
                                      target_type="organization", target_id=str(organization_id), outcome="success",
                                      metadata_json=metadata))


def get_account(session: Session, organization_id: UUID, *, create: bool = False) -> ShopBillingAccount | None:
    account = session.get(ShopBillingAccount, organization_id)
    if account is None and create:
        account = ShopBillingAccount(organization_id=organization_id, status="none", extra_locations=0,
                                     monthly_amount_cents=0, reminder_count=0, currency="CAD")
        session.add(account)
        session.flush()
    return account


def billing_applies(session: Session, organization_id: UUID) -> bool:
    if not billing_enabled():
        return False
    organization = session.get(Organization, organization_id)
    return organization is not None and not organization.billing_exempt


def current_package(session: Session, organization_id: UUID) -> str:
    account = session.get(ShopBillingAccount, organization_id)
    if account is not None and account.package_key:
        return account.package_key
    organization = session.get(Organization, organization_id)
    return (organization.selected_package if organization else None) or "starter"


def shop_features(session: Session, organization_id: UUID) -> dict:
    if not billing_applies(session, organization_id):
        return dict(ALL_FEATURES)
    return features_for(current_package(session, organization_id))


def enforce_package_feature(session: Session, organization_id: UUID, feature: str) -> None:
    if shop_features(session, organization_id).get(feature) is True:
        return
    needed = FEATURE_PACKAGE.get(feature, "pro")
    raise HTTPException(403, detail={"code": "package_upgrade_required", "feature": feature, "requiredPackage": needed,
                                     "message": f"This feature is part of the {package_name(needed)} package."})


def ordering_paused(session: Session, organization_id: UUID, now: datetime | None = None) -> bool:
    if not billing_applies(session, organization_id):
        return False
    account = session.get(ShopBillingAccount, organization_id)
    if account is None:
        return False
    if account.status == "paused":
        return True
    return account.status == "past_due" and account.grace_ends_at is not None and (now or _now()) >= account.grace_ends_at


def enforce_ordering_not_paused(session: Session, organization_id: UUID) -> None:
    if ordering_paused(session, organization_id):
        raise HTTPException(403, detail={"code": "shop_ordering_paused",
                                         "message": "Online ordering for this shop is paused right now. Please order at the counter."})


# ---------- owner emails (billing/receipt emails only; never new-order emails) ----------

def owner_email(session: Session, organization_id: UUID) -> str | None:
    return session.scalar(select(JdsUser.primary_email).join(Membership, Membership.user_id == JdsUser.id)
                          .join(Role, Role.id == Membership.role_id)
                          .where(Membership.organization_id == organization_id, Membership.status == "active", Role.key == "owner")
                          .order_by(Membership.id).limit(1))


def send_billing_email(session: Session, organization_id: UUID, subject: str, lines: list[str]) -> bool:
    from app.communications import order_alerts
    from app.communications.customer_receipts import customer_receipts_enabled

    try:
        to = owner_email(session, organization_id)
        if not to or not customer_receipts_enabled():
            logger.info("billing email skipped org=%s", organization_id)
            return False
        order_alerts.email_sender(order_alerts.AlertEmail(to=to, subject=subject, text="\n".join(lines + ["", "JDS Studio"])))
        record_usage(session, organization_id, "emails_sent")
        return True
    except Exception as error:  # noqa: BLE001
        logger.warning("billing email failed org=%s error=%s", organization_id, type(error).__name__)
        return False


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f} CAD"


# ---------- owner actions ----------

def _settings_or_error() -> BillingSquareSettings:
    if not billing_enabled():
        raise HTTPException(409, detail={"code": "billing_off", "message": "Billing is not switched on. Your shop is free during the beta."})
    settings = BillingSquareSettings.from_env()
    if not settings.is_configured():
        raise HTTPException(503, detail={"code": "billing_not_configured", "message": "Billing is not set up yet."})
    return settings


def save_card_and_subscribe(session: Session, organization_id: UUID, *, source_id: str, package_key: str | None,
                            actor: UUID | None) -> ShopBillingAccount:
    settings = _settings_or_error()
    organization = session.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(404, detail="Organization not found.")
    if organization.billing_exempt:
        raise HTTPException(409, detail={"code": "billing_exempt", "message": "Your shop is free during the beta."})
    client = square_billing.client_factory(settings)
    account = get_account(session, organization_id, create=True)
    package = package_key or account.package_key or organization.selected_package or "starter"
    try:
        if not account.square_customer_id:
            account.square_customer_id = client.create_customer(
                email=owner_email(session, organization_id) or "", name=organization.name,
                reference_id=str(organization_id), idempotency_key=f"cust-{organization_id}")
        card = client.create_card(source_id=source_id, customer_id=account.square_customer_id, idempotency_key=str(uuid4()))
        account.square_card_id = card["id"]
        account.card_brand = card.get("card_brand")
        account.card_last4 = card.get("last_4")
        account.card_exp_month = card.get("exp_month")
        account.card_exp_year = card.get("exp_year")
        if account.square_subscription_id:
            client.update_subscription(account.square_subscription_id, card_id=account.square_card_id)
        else:
            account.package_key = package
            account.monthly_amount_cents = monthly_amount_cents(package, account.extra_locations)
            subscription = client.create_subscription(
                customer_id=account.square_customer_id, card_id=account.square_card_id,
                plan_variation_id=settings.plan_variations[package], amount_cents=account.monthly_amount_cents,
                currency=account.currency, idempotency_key=f"sub-{organization_id}-{package}")
            account.square_subscription_id = subscription["id"]
            account.next_bill_on = _parse_date(subscription.get("charged_through_date")) or _parse_date(subscription.get("start_date"))
            account.status = "active"
            organization.selected_package = package
    except square_billing.BillingSquareError as error:
        session.rollback()
        raise HTTPException(402, detail={"code": error.code, "message": "Square couldn't save that card. Please check it and try again."}) from error
    _audit(session, organization_id, "billing.card_saved", actor, package=account.package_key)
    session.commit()
    return account


def change_package(session: Session, organization_id: UUID, *, package_key: str, extra_locations: int | None,
                   actor: UUID | None) -> ShopBillingAccount:
    """Takes effect on the next bill: Square swaps the plan at the start of the next billing period."""
    account = get_account(session, organization_id, create=True)
    organization = session.get(Organization, organization_id)
    if extra_locations is not None:
        account.extra_locations = max(0, extra_locations)
    if not account.square_subscription_id:
        # No subscription yet: just record the choice (same as the /build picker).
        organization.selected_package = package_key
        account.package_key = None
        account.monthly_amount_cents = monthly_amount_cents(package_key, account.extra_locations)
        _audit(session, organization_id, "billing.package_recorded", actor, package=package_key)
        session.commit()
        return account
    settings = _settings_or_error()
    client = square_billing.client_factory(settings)
    new_amount = monthly_amount_cents(package_key, account.extra_locations)
    try:
        if package_key != account.package_key:
            client.swap_plan(account.square_subscription_id, plan_variation_id=settings.plan_variations[package_key])
        client.update_subscription(account.square_subscription_id, amount_cents=new_amount, currency=account.currency)
    except square_billing.BillingSquareError as error:
        session.rollback()
        raise HTTPException(502, detail={"code": error.code, "message": "Square couldn't change the plan. Please try again."}) from error
    account.pending_package_key = package_key if package_key != account.package_key else None
    account.monthly_amount_cents = new_amount
    _audit(session, organization_id, "billing.package_change_scheduled", actor, package=package_key,
           extraLocations=account.extra_locations)
    session.commit()
    return account


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def billing_view(session: Session, organization_id: UUID) -> dict:
    organization = session.get(Organization, organization_id)
    account = session.get(ShopBillingAccount, organization_id)
    enabled = billing_enabled()
    exempt = bool(organization and organization.billing_exempt)
    package = current_package(session, organization_id)
    settings = BillingSquareSettings.from_env()
    view = {
        "enabled": enabled, "exempt": exempt, "freeDuringBeta": (not enabled) or exempt,
        "package": package, "packageName": package_name(package),
        "pendingPackage": account.pending_package_key if account else None,
        "extraLocations": account.extra_locations if account else 0,
        "monthlyAmountCents": (account.monthly_amount_cents if account and account.monthly_amount_cents else monthly_amount_cents(package, account.extra_locations if account else 0)),
        "currency": "CAD",
        "status": account.status if account else "none",
        "nextBillOn": account.next_bill_on.isoformat() if account and account.next_bill_on else None,
        "graceEndsAt": account.grace_ends_at.isoformat() if account and account.grace_ends_at else None,
        "orderingPaused": ordering_paused(session, organization_id),
        "card": ({"brand": account.card_brand, "last4": account.card_last4, "expMonth": account.card_exp_month,
                  "expYear": account.card_exp_year} if account and account.card_last4 else None),
        "features": shop_features(session, organization_id),
        "cardForm": None,
    }
    if enabled and not exempt and settings.is_configured():
        # Public values only (application id + location id are safe to expose to the browser).
        view["cardForm"] = {"applicationId": settings.application_id, "locationId": settings.location_id,
                            "sdkUrl": settings.web_sdk_url}
    return view


# ---------- Square webhook events ----------

def _account_for_subscription(session: Session, subscription_id: str | None) -> ShopBillingAccount | None:
    if not subscription_id:
        return None
    return session.scalar(select(ShopBillingAccount).where(ShopBillingAccount.square_subscription_id == subscription_id))


def _invoice_amount(invoice: dict) -> int:
    for request in invoice.get("payment_requests") or []:
        for key in ("total_completed_amount_money", "computed_amount_money"):
            money = request.get(key) or {}
            if money.get("amount"):
                return int(money["amount"])
    return 0


def handle_square_event(session: Session, event: dict, now: datetime | None = None) -> str:
    now = now or _now()
    event_id = str(event.get("event_id") or "")
    kind = str(event.get("type") or "")
    obj = (event.get("data") or {}).get("object") or {}
    if not event_id:
        return "ignored"
    if kind in {"invoice.payment_made", "invoice.scheduled_charge_failed"}:
        invoice = obj.get("invoice") or {}
        account = _account_for_subscription(session, invoice.get("subscription_id"))
        if account is None:
            return "unknown_subscription"
        if session.scalar(select(BillingPayment.id).where(BillingPayment.provider_event_id == event_id)) is not None:
            return "duplicate"
        paid = kind == "invoice.payment_made"
        payment = BillingPayment(organization_id=account.organization_id, provider_event_id=event_id,
                                 provider_invoice_id=invoice.get("id"), outcome="paid" if paid else "failed",
                                 amount_cents=_invoice_amount(invoice) or account.monthly_amount_cents,
                                 currency=account.currency, package_key=account.pending_package_key or account.package_key,
                                 period=period_of(now), occurred_at=now)
        session.add(payment)
        if paid:
            _mark_paid(session, account, now)
        else:
            _mark_failed(session, account, now)
        session.commit()
        from app.billing.cockpit import emit_payment_event
        emit_payment_event(payment)
        return "paid" if paid else "failed"
    if kind == "subscription.updated":
        subscription = obj.get("subscription") or {}
        account = _account_for_subscription(session, subscription.get("id"))
        if account is None:
            return "unknown_subscription"
        next_bill = _parse_date(subscription.get("charged_through_date"))
        if next_bill:
            account.next_bill_on = next_bill
        if subscription.get("card_id") and subscription.get("card_id") != account.square_card_id:
            account.square_card_id = subscription["card_id"]
        if subscription.get("status") in {"CANCELED", "DEACTIVATED"}:
            account.status = "cancelled"
            _audit(session, account.organization_id, "billing.subscription_cancelled")
        session.commit()
        return "updated"
    return "ignored"


def _mark_paid(session: Session, account: ShopBillingAccount, now: datetime) -> None:
    was_paused = account.status == "paused" or account.paused_at is not None
    if account.pending_package_key:
        account.package_key = account.pending_package_key
        account.pending_package_key = None
        organization = session.get(Organization, account.organization_id)
        if organization is not None:
            organization.selected_package = account.package_key
    account.status = "active"
    account.past_due_since = None
    account.grace_ends_at = None
    account.paused_at = None
    account.reminder_count = 0
    account.last_reminder_at = None
    _audit(session, account.organization_id, "billing.payment_paid")
    if was_paused:
        _audit(session, account.organization_id, "billing.ordering_resumed")
        send_billing_email(session, account.organization_id, "Your JDS ordering app is back on",
                           ["Thanks, your payment went through.", "Online ordering is switched back on for your customers."])


def _mark_failed(session: Session, account: ShopBillingAccount, now: datetime) -> None:
    if account.status not in {"past_due", "paused"}:
        account.status = "past_due"
        account.past_due_since = now
        account.grace_ends_at = now + timedelta(days=grace_days())
        account.reminder_count = 0
    _audit(session, account.organization_id, "billing.payment_failed")
    _send_reminder(session, account, now)


def _send_reminder(session: Session, account: ShopBillingAccount, now: datetime) -> None:
    deadline = account.grace_ends_at.astimezone(timezone.utc).strftime("%B %-d") if account.grace_ends_at else "soon"
    send_billing_email(session, account.organization_id, "Payment problem with your JDS ordering app", [
        f"We couldn't charge your card for this month's JDS plan ({_money(account.monthly_amount_cents)}).",
        f"Please update your card in your dashboard under Billing before {deadline}.",
        "If it's still unpaid by then, online ordering will pause until the payment goes through.",
    ])
    account.reminder_count = (account.reminder_count or 0) + 1
    account.last_reminder_at = now


def run_billing_sweep(session: Session, now: datetime | None = None) -> dict:
    """Send reminders during the grace period and pause ordering when it ends. Safe to run often."""
    now = now or _now()
    result = {"reminders": 0, "paused": 0, "skipped": not billing_enabled()}
    if result["skipped"]:
        return result
    rows = session.scalars(select(ShopBillingAccount).where(ShopBillingAccount.status == "past_due")).all()
    for account in rows:
        organization = session.get(Organization, account.organization_id)
        if organization is None or organization.billing_exempt:
            continue
        if account.grace_ends_at and now >= account.grace_ends_at:
            account.status = "paused"
            account.paused_at = now
            _audit(session, account.organization_id, "billing.ordering_paused")
            send_billing_email(session, account.organization_id, "Online ordering is paused", [
                "We still couldn't collect this month's JDS plan payment, so online ordering is paused for now.",
                "Update your card in your dashboard under Billing and it switches back on as soon as the payment goes through.",
            ])
            result["paused"] += 1
        elif (account.reminder_count or 0) < MAX_REMINDERS and (account.last_reminder_at is None or now - account.last_reminder_at >= REMINDER_EVERY):
            _send_reminder(session, account, now)
            result["reminders"] += 1
    session.commit()
    return result
