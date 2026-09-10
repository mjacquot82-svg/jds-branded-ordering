from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerRelationship(Base):
    __tablename__ = "organization_customers"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_organization_customers_org_user"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("jds_users.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(30), default="", server_default="")
    preferred_pickup_minutes: Mapped[int | None] = mapped_column(Integer)
    preferred_pickup_notes: Mapped[str | None] = mapped_column(Text)
    communication_metadata: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class StorefrontHostname(Base):
    __tablename__ = "storefront_hostnames"
    __table_args__ = (
        UniqueConstraint("hostname", name="uq_storefront_hostnames_hostname"),
        CheckConstraint("status IN ('pending','verified','disabled')", name="ck_storefront_hostnames_status"),
        Index("uq_storefront_canonical_per_org", "organization_id", unique=True, postgresql_where=text("is_canonical IS TRUE AND status = 'verified'")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    hostname: Mapped[str] = mapped_column(String(253))
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BusinessProfile(Base):
    __tablename__ = "organization_business_profiles"
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(240))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    socials: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    timezone: Mapped[str] = mapped_column(String(100), default="America/Toronto", server_default="America/Toronto")
    currency: Mapped[str] = mapped_column(String(3), default="CAD", server_default="CAD")
    tax_display_policy: Mapped[str] = mapped_column(String(30), default="exclusive", server_default="exclusive")
    pickup_instructions: Mapped[str] = mapped_column(Text, default="", server_default="")
    fulfillment_wording: Mapped[str] = mapped_column(String(120), default="Pickup", server_default="Pickup")
    operational_copy: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("organization_id", "storage_key", name="uq_media_assets_org_storage_key"),
        UniqueConstraint("organization_id", "id", name="uq_media_assets_org_id"),
        CheckConstraint("status IN ('active','archived')", name="ck_media_assets_status"),
        CheckConstraint("purpose IN ('design','product')", name="ck_media_assets_purpose"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(String(20), default="design", server_default="design")
    alt_text: Mapped[str] = mapped_column(String(300), default="", server_default="")
    byte_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("jds_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DesignWorkspace(Base):
    __tablename__ = "design_workspaces"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "published_version_id"],
            ["design_versions.organization_id", "design_versions.id"],
            name="fk_design_workspaces_org_published_version",
            ondelete="RESTRICT",
            use_alter=True,
        ),
    )
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    draft_config: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    published_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("design_versions.id", use_alter=True, ondelete="SET NULL"))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("jds_users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DesignVersion(Base):
    __tablename__ = "design_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "version_number", name="uq_design_versions_org_number"),
        UniqueConstraint("organization_id", "id", name="uq_design_versions_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "source_version_id"],
            ["design_versions.organization_id", "design_versions.id"],
            name="fk_design_versions_org_source_version",
            ondelete="RESTRICT",
            use_alter=True,
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    source_revision: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(JSON)
    published_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("jds_users.id", ondelete="SET NULL"))
    source_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("design_versions.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DesignPublication(Base):
    __tablename__ = "design_publications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "version_id"],
            ["design_versions.organization_id", "design_versions.id"],
            name="fk_design_publications_org_version",
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("design_versions.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("jds_users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DesignMediaReference(Base):
    """Normalized media reachability for safe draft and published lifecycle checks."""

    __tablename__ = "design_media_references"
    __table_args__ = (
        CheckConstraint("scope IN ('draft','published')", name="ck_design_media_references_scope"),
        CheckConstraint(
            "(scope = 'draft' AND design_version_id IS NULL) OR "
            "(scope = 'published' AND design_version_id IS NOT NULL)",
            name="ck_design_media_references_scope_version",
        ),
        UniqueConstraint(
            "organization_id", "scope", "design_version_id", "slot",
            name="uq_design_media_references_scope_slot",
        ),
        ForeignKeyConstraint(
            ["organization_id", "media_asset_id"],
            ["media_assets.organization_id", "media_assets.id"],
            name="fk_design_media_references_org_media",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "design_version_id"],
            ["design_versions.organization_id", "design_versions.id"],
            name="fk_design_media_references_org_version",
            ondelete="CASCADE",
        ),
        Index(
            "uq_design_media_references_active_draft_slot", "organization_id", "slot",
            unique=True, postgresql_where=text("scope = 'draft'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    media_asset_id: Mapped[UUID] = mapped_column(index=True)
    scope: Mapped[str] = mapped_column(String(20))
    slot: Mapped[str] = mapped_column(String(40))
    design_version_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OnboardingState(Base):
    __tablename__ = "organization_onboarding"
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[str] = mapped_column(String(30), default="in_progress", server_default="in_progress")
    completed_steps: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    current_step: Mapped[str] = mapped_column(String(50), default="business", server_default="business")
    public_ready: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    initial_setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    initial_launch_source: Mapped[str | None] = mapped_column(String(50))
    initial_launch_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("jds_users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PlatformGrant(Base):
    __tablename__ = "platform_grants"
    __table_args__ = (UniqueConstraint("user_id", "capability", name="uq_platform_grants_user_capability"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("jds_users.id", ondelete="CASCADE"), index=True)
    capability: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    granted_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("jds_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BillingPlan(Base):
    __tablename__ = "billing_plans"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    entitlements: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class OrganizationSubscription(Base):
    __tablename__ = "organization_subscriptions"
    __table_args__ = (CheckConstraint("state IN ('trialing','active','past_due','grace','cancelled')", name="ck_org_subscriptions_state"),)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    plan_key: Mapped[str] = mapped_column(ForeignKey("billing_plans.key", ondelete="RESTRICT"), index=True)
    state: Mapped[str] = mapped_column(String(20), default="trialing", server_default="trialing")
    provider: Mapped[str] = mapped_column(String(30), default="unconfigured", server_default="unconfigured")
    provider_customer_ref: Mapped[str | None] = mapped_column(String(200))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grace_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OperationalAuditEvent(Base):
    __tablename__ = "operational_audit_events"
    __table_args__ = (Index("ix_operational_audit_tenant_time", "organization_id", "occurred_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    scope: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("jds_users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str | None] = mapped_column(String(100))
    target_id: Mapped[str | None] = mapped_column(String(200))
    outcome: Mapped[str] = mapped_column(String(30))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class BillingPlanPricing(Base):
    """Central, non-hard-coded public list price for a billing plan (M2)."""

    __tablename__ = "billing_plan_pricing"
    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="ck_billing_plan_pricing_amount"),
        CheckConstraint("jds_sales_take_percent = 0", name="ck_billing_plan_pricing_jds_take"),
        CheckConstraint("interval IN ('month')", name="ck_billing_plan_pricing_interval"),
    )
    plan_key: Mapped[str] = mapped_column(ForeignKey("billing_plans.key", ondelete="CASCADE"), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), default="CAD", server_default="CAD")
    amount_cents: Mapped[int] = mapped_column(Integer)
    interval: Mapped[str] = mapped_column(String(20), default="month", server_default="month")
    jds_sales_take_percent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    public_label: Mapped[str] = mapped_column(String(120), default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DemoPendingSignup(Base):
    __tablename__ = "demo_pending_signups"
    __table_args__ = (
        UniqueConstraint("email_hash", name="uq_demo_pending_signups_email_hash"),
        CheckConstraint("status IN ('pending','claimed','expired','cancelled')", name="ck_demo_pending_signups_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), index=True)
    email_hash: Mapped[str] = mapped_column(String(64))
    business_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(200), default="", server_default="")
    desired_slug: Mapped[str | None] = mapped_column(String(63))
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_organization_id: Mapped[UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DemoActivationRequest(Base):
    __tablename__ = "demo_activation_requests"
    __table_args__ = (
        CheckConstraint(
            "processor_preference IN ('clover','square','stripe','moneris','other','not_sure')",
            name="ck_demo_activation_processor",
        ),
        CheckConstraint(
            "status IN ('requested','in_review','approved','rejected','withdrawn')",
            name="ck_demo_activation_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    requested_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("jds_users.id", ondelete="SET NULL"))
    business_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(30))
    city: Mapped[str] = mapped_column(String(120), default="", server_default="")
    desired_domain: Mapped[str | None] = mapped_column(String(253))
    processor_preference: Mapped[str] = mapped_column(String(40), default="not_sure", server_default="not_sure")
    status: Mapped[str] = mapped_column(String(30), default="requested", server_default="requested", index=True)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    quoted_plan_key: Mapped[str] = mapped_column(String(50), default="jds-standard", server_default="jds-standard")
    quoted_amount_cents: Mapped[int] = mapped_column(Integer, default=15000, server_default="15000")
    quoted_currency: Mapped[str] = mapped_column(String(3), default="CAD", server_default="CAD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DemoFunnelEvent(Base):
    __tablename__ = "demo_funnel_events"
    __table_args__ = (
        CheckConstraint(
            "event_name IN ("
            "'demo_started','logo_added','branding_changed','menu_edited',"
            "'preview_opened','demo_saved','activation_viewed','activation_requested'"
            ")",
            name="ck_demo_funnel_event_name",
        ),
        Index("ix_demo_funnel_events_org_time", "organization_id", "occurred_at"),
        Index("ix_demo_funnel_events_name", "event_name"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("jds_users.id", ondelete="SET NULL"))
    event_name: Mapped[str] = mapped_column(String(60))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

