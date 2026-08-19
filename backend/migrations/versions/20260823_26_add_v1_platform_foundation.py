"""Add remaining V1 tenant platform foundation.

Revision ID: 20260823_26
Revises: 20260822_25
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260823_26"
down_revision: str | None = "20260822_25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LADELS = "(SELECT id FROM organizations WHERE slug = 'the-guest-house')"


def upgrade() -> None:
    op.add_column("organizations", sa.Column("lifecycle_status", sa.String(20), nullable=False, server_default="active"))
    op.create_check_constraint("ck_organizations_lifecycle_status", "organizations", "lifecycle_status IN ('onboarding','active','suspended','archived')")

    op.create_table("organization_customers",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False), sa.Column("display_name", sa.String(200)), sa.Column("phone", sa.String(30), nullable=False, server_default=""),
        sa.Column("preferred_pickup_minutes", sa.Integer()), sa.Column("preferred_pickup_notes", sa.Text()),
        sa.Column("communication_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["jds_users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_organization_customers_org_user"))
    op.create_index("ix_organization_customers_organization_id", "organization_customers", ["organization_id"])
    op.create_index("ix_organization_customers_user_id", "organization_customers", ["user_id"])
    op.execute(f"""INSERT INTO organization_customers (id, organization_id, user_id, display_name, phone, preferred_pickup_minutes, preferred_pickup_notes)
        SELECT gen_random_uuid(), {LADELS}, p.user_id, u.display_name, p.phone, p.preferred_pickup_minutes, p.preferred_pickup_notes FROM customer_profiles p JOIN jds_users u ON u.id = p.user_id""")

    op.create_table("storefront_hostnames",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("hostname", sa.String(253), nullable=False), sa.Column("is_canonical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"), sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("hostname", name="uq_storefront_hostnames_hostname"),
        sa.CheckConstraint("status IN ('pending','verified','disabled')", name="ck_storefront_hostnames_status"))
    op.create_index("ix_storefront_hostnames_organization_id", "storefront_hostnames", ["organization_id"])
    op.create_index("uq_storefront_canonical_per_org", "storefront_hostnames", ["organization_id"], unique=True, postgresql_where=sa.text("is_canonical IS TRUE AND status = 'verified'"))
    op.execute(f"INSERT INTO storefront_hostnames (id, organization_id, hostname, is_canonical, status, verified_at) VALUES (gen_random_uuid(), {LADELS}, 'the-guest-house.jdsstudio.ca', true, 'verified', now())")

    op.create_table("organization_business_profiles",
        sa.Column("organization_id", sa.Uuid(), primary_key=True), sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("legal_name", sa.String(240)), sa.Column("contact_email", sa.String(320)), sa.Column("phone", sa.String(30)),
        sa.Column("address", sa.JSON(), nullable=False, server_default="{}"), sa.Column("socials", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("timezone", sa.String(100), nullable=False, server_default="America/Toronto"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("tax_display_policy", sa.String(30), nullable=False, server_default="exclusive"),
        sa.Column("pickup_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("fulfillment_wording", sa.String(120), nullable=False, server_default="Pickup"),
        sa.Column("operational_copy", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"))
    op.execute(f"INSERT INTO organization_business_profiles (organization_id, display_name, legal_name, timezone, currency, pickup_instructions) VALUES ({LADELS}, 'The Guest House', 'Ladel''s / The Guest House', 'America/Toronto', 'CAD', 'Pick up your order at the café counter.')")

    op.create_table("media_assets",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False), sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("alt_text", sa.String(300), nullable=False, server_default=""), sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.Uuid()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["jds_users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "storage_key", name="uq_media_assets_org_storage_key"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_media_assets_status"))
    op.create_index("ix_media_assets_organization_id", "media_assets", ["organization_id"])

    op.create_table("design_versions",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False), sa.Column("published_by_user_id", sa.Uuid()), sa.Column("source_version_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["jds_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_version_id"], ["design_versions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "version_number", name="uq_design_versions_org_number"))
    op.create_index("ix_design_versions_organization_id", "design_versions", ["organization_id"])
    op.create_table("design_workspaces",
        sa.Column("organization_id", sa.Uuid(), primary_key=True), sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("draft_config", sa.JSON(), nullable=False, server_default="{}"), sa.Column("published_version_id", sa.Uuid()),
        sa.Column("updated_by_user_id", sa.Uuid()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_version_id"], ["design_versions.id"], ondelete="SET NULL", use_alter=True),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["jds_users.id"], ondelete="SET NULL"))
    op.create_table("design_publications",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False), sa.Column("action", sa.String(20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid()), sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["design_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["jds_users.id"], ondelete="SET NULL"))
    op.create_index("ix_design_publications_organization_id", "design_publications", ["organization_id"])
    op.create_index("ix_design_publications_version_id", "design_publications", ["version_id"])
    op.create_foreign_key("fk_design_workspaces_published_version_id_design_versions", "design_workspaces", "design_versions", ["published_version_id"], ["id"], ondelete="SET NULL")
    default_design = """{"template":"cozy","displayName":"The Guest House","tagline":"Café & Pantry","colors":{"primary":"#6f7d5f","accent":"#b98564","background":"#f7f0e6","surface":"#ffffff","text":"#2f3328"},"typography":"classic","buttonStyle":"rounded","hero":{"mode":"image","mediaId":null},"categoryPresentation":"cards","productCardPresentation":"comfortable","navigation":"tabs","sections":["hero","announcement","categories","quickOrder"],"pwa":{"shortName":"Guest House","themeColor":"#6f7d5f","backgroundColor":"#f7f0e6"}}"""
    op.get_bind().exec_driver_sql(f"INSERT INTO design_versions (id, organization_id, version_number, source_revision, config) VALUES (gen_random_uuid(), {LADELS}, 1, 1, '{default_design}'::json)")
    op.execute(f"INSERT INTO design_workspaces (organization_id, revision, draft_config, published_version_id) SELECT {LADELS}, 1, config, id FROM design_versions WHERE organization_id={LADELS} AND version_number=1")
    op.execute(f"INSERT INTO design_publications (id, organization_id, version_id, action) SELECT gen_random_uuid(), {LADELS}, id, 'publish' FROM design_versions WHERE organization_id={LADELS} AND version_number=1")

    op.create_table("organization_onboarding",
        sa.Column("organization_id", sa.Uuid(), primary_key=True), sa.Column("state", sa.String(30), nullable=False, server_default="in_progress"),
        sa.Column("completed_steps", sa.JSON(), nullable=False, server_default="[]"), sa.Column("current_step", sa.String(50), nullable=False, server_default="business"),
        sa.Column("public_ready", sa.Boolean(), nullable=False, server_default="false"), sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"))
    op.execute(f"INSERT INTO organization_onboarding (organization_id, state, completed_steps, current_step, public_ready) VALUES ({LADELS}, 'complete', '[\"business\",\"storefront\",\"hours\",\"fulfillment\",\"design\",\"catalog\",\"clover\"]'::json, 'complete', true)")

    op.create_table("platform_grants",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("user_id", sa.Uuid(), nullable=False), sa.Column("capability", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"), sa.Column("granted_by_user_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["jds_users.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["granted_by_user_id"], ["jds_users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "capability", name="uq_platform_grants_user_capability"))
    op.create_index("ix_platform_grants_user_id", "platform_grants", ["user_id"])
    op.create_table("billing_plans", sa.Column("key", sa.String(50), primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("entitlements", sa.JSON(), nullable=False, server_default="{}"), sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))
    op.get_bind().exec_driver_sql("INSERT INTO billing_plans (key,name,entitlements) VALUES ('core','Core','{\"designStudio\":true,\"notifications\":false,\"loyalty\":false}'::json), ('engagement','Engagement','{\"designStudio\":true,\"notifications\":true,\"loyalty\":true}'::json)")
    op.create_table("organization_subscriptions",
        sa.Column("organization_id", sa.Uuid(), primary_key=True), sa.Column("plan_key", sa.String(50), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="trialing"), sa.Column("provider", sa.String(30), nullable=False, server_default="local"),
        sa.Column("provider_customer_ref", sa.String(200)), sa.Column("trial_ends_at", sa.DateTime(timezone=True)), sa.Column("grace_ends_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["plan_key"], ["billing_plans.key"], ondelete="RESTRICT"),
        sa.CheckConstraint("state IN ('trialing','active','past_due','grace','cancelled')", name="ck_org_subscriptions_state"))
    op.create_index("ix_organization_subscriptions_plan_key", "organization_subscriptions", ["plan_key"])
    op.execute(f"INSERT INTO organization_subscriptions (organization_id,plan_key,state) VALUES ({LADELS},'engagement','active')")

    op.create_table("operational_audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid()), sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid()), sa.Column("action", sa.String(120), nullable=False), sa.Column("target_type", sa.String(100)),
        sa.Column("target_id", sa.String(200)), sa.Column("outcome", sa.String(30), nullable=False), sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["actor_user_id"], ["jds_users.id"], ondelete="SET NULL"))
    op.create_index("ix_operational_audit_events_organization_id", "operational_audit_events", ["organization_id"])
    op.create_index("ix_operational_audit_events_action", "operational_audit_events", ["action"])
    op.create_index("ix_operational_audit_tenant_time", "operational_audit_events", ["organization_id", "occurred_at"])

    # Notifications are relationships with a merchant, not global account settings.
    for table in ("customer_notification_preferences", "web_push_subscriptions", "push_delivery_attempts"):
        op.add_column(table, sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.execute(f"UPDATE customer_notification_preferences SET organization_id={LADELS}")
    op.execute(f"UPDATE web_push_subscriptions SET organization_id={LADELS}")
    op.execute("UPDATE push_delivery_attempts d SET organization_id=a.organization_id FROM push_announcements a WHERE d.announcement_id=a.id")
    op.drop_constraint("uq_customer_notification_preference", "customer_notification_preferences", type_="unique")
    op.create_unique_constraint("uq_customer_notification_preference", "customer_notification_preferences", ["organization_id", "customer_user_id", "notification_kind"])
    op.drop_constraint("uq_web_push_subscriptions_endpoint_fingerprint", "web_push_subscriptions", type_="unique")
    op.create_unique_constraint("uq_web_push_subscription_org_endpoint", "web_push_subscriptions", ["organization_id", "endpoint_fingerprint"])
    notification_names = {
        "customer_notification_preferences": ("fk_cnp_org", "ix_customer_notification_preferences_organization_id"),
        "web_push_subscriptions": ("fk_wps_org", "ix_web_push_subscriptions_organization_id"),
        "push_delivery_attempts": ("fk_pda_org", "ix_push_delivery_attempts_organization_id"),
    }
    for table, (fk_name, ix_name) in notification_names.items():
        op.create_foreign_key(fk_name, table, "organizations", ["organization_id"], ["id"], ondelete="CASCADE")
        op.create_index(ix_name, table, ["organization_id"])
        op.alter_column(table, "organization_id", nullable=False)

    # Loyalty carries tenant ownership at every directly queried boundary.
    op.add_column("loyalty_program_products", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.add_column("customer_loyalty_events", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE loyalty_program_products p SET organization_id=l.organization_id FROM loyalty_programs l WHERE p.loyalty_program_id=l.id")
    op.execute("UPDATE customer_loyalty_events e SET organization_id=l.organization_id FROM loyalty_programs l WHERE e.loyalty_program_id=l.id")
    loyalty_names = {"loyalty_program_products": ("fk_lpp_org", "ix_loyalty_program_products_organization_id"), "customer_loyalty_events": ("fk_cle_org", "ix_customer_loyalty_events_organization_id")}
    for table, (fk_name, ix_name) in loyalty_names.items():
        op.create_foreign_key(fk_name, table, "organizations", ["organization_id"], ["id"], ondelete="CASCADE")
        op.create_index(ix_name, table, ["organization_id"])
        op.alter_column(table, "organization_id", nullable=False)


def downgrade() -> None:
    # The expand migration can be removed only while all new data belongs to the
    # compatibility tenant. Refuse a downgrade that would discard real tenant state.
    op.execute(f"""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM storefront_hostnames WHERE organization_id <> {LADELS})
         OR EXISTS (SELECT 1 FROM organization_customers WHERE organization_id <> {LADELS})
         OR EXISTS (SELECT 1 FROM media_assets WHERE organization_id <> {LADELS})
      THEN RAISE EXCEPTION 'cannot safely downgrade V1 multi-tenant platform data'; END IF;
    END $$""")
    for table, (fk_name, ix_name) in {"customer_loyalty_events": ("fk_cle_org", "ix_customer_loyalty_events_organization_id"), "loyalty_program_products": ("fk_lpp_org", "ix_loyalty_program_products_organization_id")}.items():
        op.drop_index(ix_name, table_name=table); op.drop_constraint(fk_name, table, type_="foreignkey"); op.drop_column(table, "organization_id")
    notification_names = {
        "push_delivery_attempts": ("fk_pda_org", "ix_push_delivery_attempts_organization_id"),
        "web_push_subscriptions": ("fk_wps_org", "ix_web_push_subscriptions_organization_id"),
        "customer_notification_preferences": ("fk_cnp_org", "ix_customer_notification_preferences_organization_id"),
    }
    op.drop_constraint("uq_web_push_subscription_org_endpoint", "web_push_subscriptions", type_="unique")
    op.create_unique_constraint("uq_web_push_subscriptions_endpoint_fingerprint", "web_push_subscriptions", ["endpoint_fingerprint"])
    op.drop_constraint("uq_customer_notification_preference", "customer_notification_preferences", type_="unique")
    op.create_unique_constraint("uq_customer_notification_preference", "customer_notification_preferences", ["customer_user_id", "notification_kind"])
    for table, (fk_name, ix_name) in notification_names.items():
        op.drop_index(ix_name, table_name=table); op.drop_constraint(fk_name, table, type_="foreignkey"); op.drop_column(table, "organization_id")
    op.drop_constraint("fk_design_workspaces_published_version_id_design_versions", "design_workspaces", type_="foreignkey")
    for table in (
        "operational_audit_events", "organization_subscriptions", "billing_plans",
        "platform_grants", "organization_onboarding", "design_publications",
        "design_workspaces", "design_versions", "media_assets",
        "organization_business_profiles", "storefront_hostnames", "organization_customers",
    ):
        op.drop_table(table)
    op.drop_constraint("ck_organizations_lifecycle_status", "organizations", type_="check")
    op.drop_column("organizations", "lifecycle_status")
