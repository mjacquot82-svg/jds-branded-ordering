"""Repair V1 platform integrity and remove deployment-specific seeds.

Revision ID: 20260819_27
Revises: 20260823_26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_27"
down_revision: str | None = "20260823_26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Every subscriber or loyalty participant must have an explicit merchant
    # relationship before composite tenant integrity can be enforced.
    op.execute("""
        INSERT INTO organization_customers
            (id, organization_id, user_id, display_name, phone)
        SELECT gen_random_uuid(), source.organization_id, source.user_id,
               users.display_name, ''
        FROM (
            SELECT organization_id, customer_user_id AS user_id
              FROM customer_notification_preferences
            UNION
            SELECT organization_id, customer_user_id
              FROM web_push_subscriptions
            UNION
            SELECT organization_id, customer_user_id
              FROM customer_loyalty_events
        ) source
        JOIN jds_users users ON users.id = source.user_id
        ON CONFLICT (organization_id, user_id) DO NOTHING
    """)

    op.create_unique_constraint("uq_loyalty_programs_organization_id", "loyalty_programs", ["organization_id", "id"])
    op.create_unique_constraint("uq_media_assets_org_id", "media_assets", ["organization_id", "id"])
    op.create_unique_constraint("uq_design_versions_org_id", "design_versions", ["organization_id", "id"])
    op.create_unique_constraint("uq_web_push_subscriptions_org_id", "web_push_subscriptions", ["organization_id", "id"])
    op.create_unique_constraint("uq_push_announcements_org_id", "push_announcements", ["organization_id", "id"])

    op.create_foreign_key("fk_customer_notification_preferences_org_customer", "customer_notification_preferences", "organization_customers", ["organization_id", "customer_user_id"], ["organization_id", "user_id"], ondelete="CASCADE")
    op.create_foreign_key("fk_web_push_subscriptions_org_customer", "web_push_subscriptions", "organization_customers", ["organization_id", "customer_user_id"], ["organization_id", "user_id"], ondelete="CASCADE")
    op.create_foreign_key("fk_push_delivery_attempts_org_announcement", "push_delivery_attempts", "push_announcements", ["organization_id", "announcement_id"], ["organization_id", "id"], ondelete="CASCADE")
    op.create_foreign_key("fk_push_delivery_attempts_org_subscription", "push_delivery_attempts", "web_push_subscriptions", ["organization_id", "subscription_id"], ["organization_id", "id"], ondelete="CASCADE")
    op.create_foreign_key("fk_loyalty_program_products_org_program", "loyalty_program_products", "loyalty_programs", ["organization_id", "loyalty_program_id"], ["organization_id", "id"], ondelete="CASCADE")
    op.create_foreign_key("fk_loyalty_program_products_org_product", "loyalty_program_products", "products", ["organization_id", "product_id"], ["organization_id", "id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_customer_loyalty_events_org_program", "customer_loyalty_events", "loyalty_programs", ["organization_id", "loyalty_program_id"], ["organization_id", "id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_customer_loyalty_events_org_order", "customer_loyalty_events", "orders", ["organization_id", "related_order_id"], ["organization_id", "id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_customer_loyalty_events_org_customer", "customer_loyalty_events", "organization_customers", ["organization_id", "customer_user_id"], ["organization_id", "user_id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_design_workspaces_org_published_version", "design_workspaces", "design_versions", ["organization_id", "published_version_id"], ["organization_id", "id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_design_versions_org_source_version", "design_versions", "design_versions", ["organization_id", "source_version_id"], ["organization_id", "id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_design_publications_org_version", "design_publications", "design_versions", ["organization_id", "version_id"], ["organization_id", "id"], ondelete="RESTRICT")

    op.create_table(
        "design_media_references",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("media_asset_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("slot", sa.String(40), nullable=False),
        sa.Column("design_version_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id", "media_asset_id"], ["media_assets.organization_id", "media_assets.id"], name="fk_design_media_references_org_media", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id", "design_version_id"], ["design_versions.organization_id", "design_versions.id"], name="fk_design_media_references_org_version", ondelete="CASCADE"),
        sa.CheckConstraint("scope IN ('draft','published')", name="ck_design_media_references_scope"),
        sa.CheckConstraint("(scope = 'draft' AND design_version_id IS NULL) OR (scope = 'published' AND design_version_id IS NOT NULL)", name="ck_design_media_references_scope_version"),
        sa.UniqueConstraint("organization_id", "scope", "design_version_id", "slot", name="uq_design_media_references_scope_slot"),
    )
    op.create_index("ix_design_media_references_organization_id", "design_media_references", ["organization_id"])
    op.create_index("ix_design_media_references_media_asset_id", "design_media_references", ["media_asset_id"])
    op.create_index("uq_design_media_references_active_draft_slot", "design_media_references", ["organization_id", "slot"], unique=True, postgresql_where=sa.text("scope = 'draft'"))
    op.execute("""
        INSERT INTO design_media_references
            (id, organization_id, media_asset_id, scope, slot, design_version_id)
        SELECT gen_random_uuid(), w.organization_id,
               (w.draft_config->>'logoMediaId')::uuid, 'draft', 'logo', NULL::uuid
          FROM design_workspaces w
         WHERE COALESCE(w.draft_config->>'logoMediaId', '') ~* '^[0-9a-f-]{36}$'
        UNION ALL
        SELECT gen_random_uuid(), w.organization_id,
               (w.draft_config->'hero'->>'mediaId')::uuid, 'draft', 'hero', NULL::uuid
          FROM design_workspaces w
         WHERE COALESCE(w.draft_config->'hero'->>'mediaId', '') ~* '^[0-9a-f-]{36}$'
        UNION ALL
        SELECT gen_random_uuid(), v.organization_id,
               (v.config->>'logoMediaId')::uuid, 'published', 'logo', v.id
          FROM design_versions v
         WHERE COALESCE(v.config->>'logoMediaId', '') ~* '^[0-9a-f-]{36}$'
        UNION ALL
        SELECT gen_random_uuid(), v.organization_id,
               (v.config->'hero'->>'mediaId')::uuid, 'published', 'hero', v.id
          FROM design_versions v
         WHERE COALESCE(v.config->'hero'->>'mediaId', '') ~* '^[0-9a-f-]{36}$'
    """)

    # Hostnames and commercial plans are deployment/application configuration,
    # never immutable schema seed data.
    op.execute("DELETE FROM storefront_hostnames WHERE hostname = 'the-guest-house.jdsstudio.ca'")
    op.execute("DELETE FROM organization_subscriptions")
    op.execute("DELETE FROM billing_plans")
    op.alter_column("organization_subscriptions", "provider", server_default="unconfigured")


def downgrade() -> None:
    op.alter_column("organization_subscriptions", "provider", server_default="local")
    op.drop_index("uq_design_media_references_active_draft_slot", table_name="design_media_references")
    op.drop_index("ix_design_media_references_media_asset_id", table_name="design_media_references")
    op.drop_index("ix_design_media_references_organization_id", table_name="design_media_references")
    op.drop_table("design_media_references")
    for name, table in (
        ("fk_design_publications_org_version", "design_publications"),
        ("fk_design_versions_org_source_version", "design_versions"),
        ("fk_design_workspaces_org_published_version", "design_workspaces"),
        ("fk_customer_loyalty_events_org_customer", "customer_loyalty_events"),
        ("fk_customer_loyalty_events_org_order", "customer_loyalty_events"),
        ("fk_customer_loyalty_events_org_program", "customer_loyalty_events"),
        ("fk_loyalty_program_products_org_product", "loyalty_program_products"),
        ("fk_loyalty_program_products_org_program", "loyalty_program_products"),
        ("fk_push_delivery_attempts_org_subscription", "push_delivery_attempts"),
        ("fk_push_delivery_attempts_org_announcement", "push_delivery_attempts"),
        ("fk_web_push_subscriptions_org_customer", "web_push_subscriptions"),
        ("fk_customer_notification_preferences_org_customer", "customer_notification_preferences"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
    op.drop_constraint("uq_push_announcements_org_id", "push_announcements", type_="unique")
    op.drop_constraint("uq_web_push_subscriptions_org_id", "web_push_subscriptions", type_="unique")
    op.drop_constraint("uq_design_versions_org_id", "design_versions", type_="unique")
    op.drop_constraint("uq_media_assets_org_id", "media_assets", type_="unique")
    op.drop_constraint("uq_loyalty_programs_organization_id", "loyalty_programs", type_="unique")
