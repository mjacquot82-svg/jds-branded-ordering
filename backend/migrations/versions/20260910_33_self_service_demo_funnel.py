"""M2 self-service demo funnel: commercial mode, activation leads, funnel events.

Revision ID: 20260910_33
Revises: 20260910_32
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_33"
down_revision: str | None = "20260910_32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("commercial_mode", sa.String(length=20), nullable=False, server_default="live"),
    )
    op.create_check_constraint(
        "ck_organizations_commercial_mode",
        "organizations",
        "commercial_mode IN ('prospect', 'live')",
    )
    # Existing merchants remain live paying/legacy tenants.
    op.execute("UPDATE organizations SET commercial_mode = 'live'")

    op.create_table(
        "billing_plan_pricing",
        sa.Column("plan_key", sa.String(length=50), sa.ForeignKey("billing_plans.key", ondelete="CASCADE"), primary_key=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="CAD"),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("interval", sa.String(length=20), nullable=False, server_default="month"),
        sa.Column("jds_sales_take_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("public_label", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount_cents >= 0", name="ck_billing_plan_pricing_amount"),
        sa.CheckConstraint("jds_sales_take_percent = 0", name="ck_billing_plan_pricing_jds_take"),
        sa.CheckConstraint("interval IN ('month')", name="ck_billing_plan_pricing_interval"),
    )

    op.execute(
        """
        INSERT INTO billing_plans (key, name, entitlements, is_active)
        VALUES
          ('jds-demo', 'JDS Free Demo', '{"designStudio": true, "demoCatalog": true, "commerce": false, "staff": false, "notifications": false, "loyalty": false, "customDomain": false}'::json, true),
          ('jds-standard', 'JDS Branded Ordering', '{"designStudio": true, "demoCatalog": true, "commerce": true, "staff": true, "notifications": true, "loyalty": true, "customDomain": true}'::json, true)
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO billing_plan_pricing (plan_key, currency, amount_cents, interval, jds_sales_take_percent, public_label)
        VALUES
          ('jds-demo', 'CAD', 0, 'month', 0, 'Free demo'),
          ('jds-standard', 'CAD', 15000, 'month', 0, 'JDS Branded Ordering')
        ON CONFLICT (plan_key) DO NOTHING
        """
    )

    op.create_table(
        "demo_pending_signups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("business_name", sa.String(length=200), nullable=False),
        sa.Column("contact_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("desired_slug", sa.String(length=63)),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("claimed_organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending','claimed','expired','cancelled')", name="ck_demo_pending_signups_status"),
        sa.UniqueConstraint("email_hash", name="uq_demo_pending_signups_email_hash"),
    )
    op.create_index("ix_demo_pending_signups_email", "demo_pending_signups", ["email"])
    op.create_index("ix_demo_pending_signups_expires_at", "demo_pending_signups", ["expires_at"])

    op.create_table(
        "demo_activation_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), sa.ForeignKey("jds_users.id", ondelete="SET NULL")),
        sa.Column("business_name", sa.String(length=200), nullable=False),
        sa.Column("contact_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("phone", sa.String(length=30)),
        sa.Column("city", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("desired_domain", sa.String(length=253)),
        sa.Column("processor_preference", sa.String(length=40), nullable=False, server_default="not_sure"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="requested"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("quoted_plan_key", sa.String(length=50), nullable=False, server_default="jds-standard"),
        sa.Column("quoted_amount_cents", sa.Integer(), nullable=False, server_default="15000"),
        sa.Column("quoted_currency", sa.String(length=3), nullable=False, server_default="CAD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "processor_preference IN ('clover','square','stripe','moneris','other','not_sure')",
            name="ck_demo_activation_processor",
        ),
        sa.CheckConstraint(
            "status IN ('requested','in_review','approved','rejected','withdrawn')",
            name="ck_demo_activation_status",
        ),
    )
    op.create_index("ix_demo_activation_requests_organization_id", "demo_activation_requests", ["organization_id"])
    op.create_index("ix_demo_activation_requests_status", "demo_activation_requests", ["status"])
    op.create_index("ix_demo_activation_requests_created_at", "demo_activation_requests", ["created_at"])

    op.create_table(
        "demo_funnel_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("jds_users.id", ondelete="SET NULL")),
        sa.Column("event_name", sa.String(length=60), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "event_name IN ("
            "'demo_started','logo_added','branding_changed','menu_edited',"
            "'preview_opened','demo_saved','activation_viewed','activation_requested'"
            ")",
            name="ck_demo_funnel_event_name",
        ),
    )
    op.create_index("ix_demo_funnel_events_org_time", "demo_funnel_events", ["organization_id", "occurred_at"])
    op.create_index("ix_demo_funnel_events_name", "demo_funnel_events", ["event_name"])


def downgrade() -> None:
    op.drop_table("demo_funnel_events")
    op.drop_table("demo_activation_requests")
    op.drop_table("demo_pending_signups")
    op.drop_table("billing_plan_pricing")
    # Remove only the M2-seeded plans (do not touch unrelated billing_plans rows).
    op.execute("DELETE FROM organization_subscriptions WHERE plan_key IN ('jds-demo', 'jds-standard')")
    op.execute("DELETE FROM billing_plans WHERE key IN ('jds-demo', 'jds-standard')")
    op.drop_constraint("ck_organizations_commercial_mode", "organizations", type_="check")
    op.drop_column("organizations", "commercial_mode")
