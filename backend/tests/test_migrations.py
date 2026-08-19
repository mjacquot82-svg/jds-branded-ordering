from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.availability import models as availability_models  # noqa: F401
from app.catalog import models as catalog_models  # noqa: F401
from app.clover import models as clover_models  # noqa: F401
from app.orders import models as order_models  # noqa: F401
from app.jds_auth import models as auth_models  # noqa: F401
from app.loyalty import models as loyalty_models  # noqa: F401
from app.db.base import Base
from app.db.migrate import (
    MigrationBootstrapError,
    _alembic_config,
    migrate_database,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def make_alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_migration_config_preserves_percent_encoded_database_urls() -> None:
    database_url = (
        "postgresql+psycopg://postgres.project:p%40ss%25word@"
        "pooler.example.com:5432/postgres"
    )

    assert _alembic_config(database_url).get_main_option("sqlalchemy.url") == database_url


@pytest.mark.postgresql
def test_catalog_migration_upgrades_and_downgrades(postgresql_url: str) -> None:
    config = make_alembic_config(postgresql_url)
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["20260822_25"]

    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine(postgresql_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert context.get_current_revision() == "20260822_25"

        assert set(inspect(engine).get_table_names()) >= {
            "alembic_version",
            "categories",
            "products",
            "product_variants",
            "modifier_groups",
            "modifier_options",
            "product_modifier_groups",
            "business_settings",
            "business_hours",
            "business_closures",
            "product_availability",
            "product_availability_overrides",
            "orders",
            "order_items",
            "order_item_modifiers",
            "clover_installations",
            "clover_payment_events",
            "jds_applications",
            "organizations",
            "jds_users",
            "external_identities",
            "auth_roles",
            "auth_permissions",
            "auth_role_permissions",
            "organization_memberships",
            "owner_sessions",
            "owner_invitations",
            "security_audit_events",
            "auth_rate_limit_buckets",
            "staff_pin_credentials",
            "customer_profiles",
            "customer_notification_preferences",
            "web_push_subscriptions",
            "push_announcements",
            "push_delivery_attempts",
            "loyalty_programs",
            "loyalty_program_products",
            "customer_loyalty_events",
        }
        currency_column = next(
            column
            for column in inspect(engine).get_columns("orders")
            if column["name"] == "currency"
        )
        assert "CAD" in str(currency_column["default"])
        lunch_special_column = next(
            column
            for column in inspect(engine).get_columns("products")
            if column["name"] == "is_lunch_special"
        )
        assert lunch_special_column["nullable"] is False
        assert any(
            index["name"] == "uq_products_single_lunch_special"
            and index["unique"]
            for index in inspect(engine).get_indexes("products")
        )

        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()).isdisjoint(
            {
                "categories",
                "products",
                "product_variants",
                "modifier_groups",
                "modifier_options",
                "product_modifier_groups",
                "business_settings",
                "business_hours",
                "business_closures",
                "product_availability",
                "product_availability_overrides",
                "orders",
                "order_items",
                "order_item_modifiers",
                "clover_installations",
                "clover_payment_events",
                "jds_applications",
                "organizations",
                "jds_users",
                "external_identities",
                "auth_roles",
                "auth_permissions",
                "auth_role_permissions",
                "organization_memberships",
                "owner_sessions",
                "owner_invitations",
                "security_audit_events",
                "auth_rate_limit_buckets",
                "staff_pin_credentials",
                "customer_profiles",
                "customer_notification_preferences",
                "web_push_subscriptions",
                "push_announcements",
                "push_delivery_attempts",
                "loyalty_programs",
                "loyalty_program_products",
                "customer_loyalty_events",
            }
        )
    finally:
        engine.dispose()

    command.upgrade(config, "head")


@pytest.mark.postgresql
def test_catalog_models_match_migration(postgresql_url: str) -> None:
    config = make_alembic_config(postgresql_url)
    command.upgrade(config, "head")

    engine = create_engine(postgresql_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "compare_type": True,
                    "target_metadata": Base.metadata,
                },
            )
            differences = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert differences == []


@pytest.mark.postgresql
def test_tenant_catalog_migration_backfills_baseline_rows_once(
    postgresql_url: str,
) -> None:
    config = make_alembic_config(postgresql_url)
    command.downgrade(config, "base")
    command.upgrade(config, "20260818_20")
    engine = create_engine(postgresql_url)
    try:
        with engine.begin() as connection:
            category_id = connection.scalar(
                text(
                    "INSERT INTO categories (slug, name) "
                    "VALUES ('baseline', 'Baseline') RETURNING id"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO products (category_id, slug, name, base_price_cents) "
                    "VALUES (:category_id, 'baseline-product', 'Baseline product', 100)"
                ),
                {"category_id": category_id},
            )
            connection.execute(
                text(
                    "INSERT INTO modifier_groups "
                    "(key, name, selection_type, is_required, minimum_selections, "
                    "maximum_selections) VALUES "
                    "('baseline-group', 'Baseline group', 'single', false, 0, 1)"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            organization_id = connection.scalar(
                text("SELECT id FROM organizations WHERE slug = 'the-guest-house'")
            )
            assert organization_id is not None
            for table_name in (
                "categories",
                "products",
                "modifier_groups",
                "business_settings",
            ):
                assert connection.scalar(
                    text(
                        f"SELECT count(*) FROM {table_name} "
                        "WHERE organization_id = :organization_id"
                    ),
                    {"organization_id": organization_id},
                ) == connection.scalar(text(f"SELECT count(*) FROM {table_name}"))
                assert connection.scalar(
                    text(f"SELECT count(*) FROM {table_name} WHERE organization_id IS NULL")
                ) == 0
    finally:
        engine.dispose()

    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.mark.postgresql
def test_tenant_availability_migration_backfills_and_enforces_ownership(
    postgresql_url: str,
) -> None:
    config = make_alembic_config(postgresql_url)
    command.downgrade(config, "base")
    command.upgrade(config, "20260819_21")
    engine = create_engine(postgresql_url)
    try:
        with engine.begin() as connection:
            organization_id = connection.scalar(
                text("SELECT id FROM organizations WHERE slug = 'the-guest-house'")
            )
            settings_id = connection.scalar(
                text(
                    "SELECT id FROM business_settings "
                    "WHERE organization_id = :organization_id"
                ),
                {"organization_id": organization_id},
            )
            category_id = connection.scalar(
                text(
                    "INSERT INTO categories (organization_id, slug, name) "
                    "VALUES (:organization_id, 'availability', 'Availability') "
                    "RETURNING id"
                ),
                {"organization_id": organization_id},
            )
            product_id = connection.scalar(
                text(
                    "INSERT INTO products "
                    "(organization_id, category_id, slug, name, base_price_cents) "
                    "VALUES (:organization_id, :category_id, 'available', "
                    "'Available', 100) RETURNING id"
                ),
                {"organization_id": organization_id, "category_id": category_id},
            )
            connection.execute(
                text(
                    "INSERT INTO business_hours "
                    "(business_settings_id, weekday, is_closed) "
                    "VALUES (:settings_id, 0, true)"
                ),
                {"settings_id": settings_id},
            )
            connection.execute(
                text(
                    "INSERT INTO business_closures "
                    "(business_settings_id, business_date) "
                    "VALUES (:settings_id, '2026-12-25')"
                ),
                {"settings_id": settings_id},
            )
            connection.execute(
                text(
                    "INSERT INTO product_availability (product_id, default_available) "
                    "VALUES (:product_id, false)"
                ),
                {"product_id": product_id},
            )
            connection.execute(
                text(
                    "INSERT INTO product_availability_overrides "
                    "(product_id, business_date, is_available) "
                    "VALUES (:product_id, '2026-12-25', true)"
                ),
                {"product_id": product_id},
            )

        command.upgrade(config, "head")
        inspector = inspect(engine)
        with engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() == "20260822_25"
            for table_name in (
                "business_hours",
                "business_closures",
                "product_availability",
                "product_availability_overrides",
            ):
                columns = {column["name"]: column for column in inspector.get_columns(table_name)}
                assert columns["organization_id"]["nullable"] is False
                assert connection.scalar(
                    text(
                        f"SELECT count(*) FROM {table_name} "
                        "WHERE organization_id = :organization_id"
                    ),
                    {"organization_id": organization_id},
                ) == 1
            assert {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("business_hours")
            } >= {"uq_business_hours_organization_weekday"}
            assert {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("business_closures")
            } >= {"uq_business_closures_organization_date"}
            assert {
                index["name"]
                for index in inspector.get_indexes("product_availability_overrides")
            } >= {"ix_product_availability_overrides_organization_date"}

        tenant_b_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO organizations (id, slug, name) "
                    "VALUES (:id, 'migration-tenant-b', 'Migration Tenant B')"
                ),
                {"id": tenant_b_id},
            )
            settings_b_id = connection.scalar(
                text(
                    "INSERT INTO business_settings (organization_id, timezone) "
                    "VALUES (:id, 'UTC') RETURNING id"
                ),
                {"id": tenant_b_id},
            )
            connection.execute(
                text(
                    "INSERT INTO business_hours "
                    "(organization_id, business_settings_id, weekday, is_closed) "
                    "VALUES (:organization_id, :settings_id, 0, true)"
                ),
                {"organization_id": tenant_b_id, "settings_id": settings_b_id},
            )
            connection.execute(
                text(
                    "INSERT INTO business_closures "
                    "(organization_id, business_settings_id, business_date) "
                    "VALUES (:organization_id, :settings_id, '2026-12-25')"
                ),
                {"organization_id": tenant_b_id, "settings_id": settings_b_id},
            )

        with pytest.raises(SQLAlchemyError, match="cannot safely downgrade"):
            command.downgrade(config, "20260819_21")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM business_settings WHERE organization_id = :id"
                ),
                {"id": tenant_b_id},
            )
            connection.execute(
                text("DELETE FROM organizations WHERE id = :id"), {"id": tenant_b_id}
            )
    finally:
        engine.dispose()


@pytest.mark.postgresql
def test_tenant_order_migration_backfills_constraints_and_refuses_unsafe_downgrade(
    postgresql_url: str,
) -> None:
    config = make_alembic_config(postgresql_url)
    command.downgrade(config, "base")
    command.upgrade(config, "20260819_22")
    engine = create_engine(postgresql_url)
    try:
        with engine.begin() as connection:
            organization_id = connection.scalar(
                text("SELECT id FROM organizations WHERE slug = 'the-guest-house'")
            )
            order_id = connection.scalar(
                text(
                    "INSERT INTO orders (idempotency_key, request_fingerprint, "
                    "public_access_token, guest_name, guest_email, guest_phone, "
                    "requested_pickup_at, business_timezone, subtotal_cents, "
                    "tax_cents, total_cents, expires_at) VALUES "
                    "('historical', :fingerprint, 'shared-token', 'Historical', "
                    "'history@example.com', '+15195550123', now() + interval '1 hour', "
                    "'America/Toronto', 100, 0, 100, now() + interval '30 minutes') "
                    "RETURNING id"
                ),
                {"fingerprint": "a" * 64},
            )
        command.upgrade(config, "head")
        inspector = inspect(engine)
        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT organization_id FROM orders WHERE id = :id"),
                {"id": order_id},
            ) == organization_id
            assert MigrationContext.configure(connection).get_current_revision() == "20260822_25"
        assert {c["name"] for c in inspector.get_unique_constraints("orders")} >= {
            "uq_orders_organization_idempotency_key",
            "uq_orders_organization_public_access_token",
        }
        assert {i["name"] for i in inspector.get_indexes("orders")} >= {
            "ix_orders_organization_active_queue",
            "ix_orders_organization_customer_created",
            "ix_orders_organization_fulfillment_pickup",
        }

        command.downgrade(config, "20260819_22")
        command.upgrade(config, "head")
        with engine.begin() as connection:
            tenant_b = uuid4()
            connection.execute(
                text("INSERT INTO organizations (id, slug, name) VALUES (:id, 'order-tenant-b', 'Order Tenant B')"),
                {"id": tenant_b},
            )
            connection.execute(
                text(
                    "INSERT INTO orders (organization_id, idempotency_key, request_fingerprint, "
                    "public_access_token, guest_name, guest_email, guest_phone, requested_pickup_at, "
                    "business_timezone, subtotal_cents, tax_cents, total_cents, expires_at) VALUES "
                    "(:organization_id, 'historical', :fingerprint, 'shared-token', 'Tenant B', "
                    "'b@example.com', '+15195550124', now() + interval '1 hour', "
                    "'America/Toronto', 100, 0, 100, now() + interval '30 minutes')"
                ),
                {"organization_id": tenant_b, "fingerprint": "b" * 64},
            )
        with pytest.raises(SQLAlchemyError, match="cannot safely downgrade tenant order data"):
            command.downgrade(config, "20260819_22")
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM orders WHERE organization_id = :organization_id"),
                {"organization_id": tenant_b},
            )
            connection.execute(
                text("DELETE FROM organizations WHERE id = :organization_id"),
                {"organization_id": tenant_b},
            )
    finally:
        engine.dispose()

    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.mark.postgresql
def test_auth_tenant_migration_binds_staff_credentials_and_refuses_unsafe_downgrade(
    postgresql_url: str,
) -> None:
    config = make_alembic_config(postgresql_url)
    command.downgrade(config, "base")
    command.upgrade(config, "20260820_23")
    engine = create_engine(postgresql_url)
    user_id = uuid4()
    with engine.begin() as connection:
        organization_id = connection.scalar(text("SELECT id FROM organizations WHERE slug = 'the-guest-house'"))
        application_id = uuid4()
        role_id = uuid4()
        connection.execute(text("INSERT INTO jds_applications (id, key, name) VALUES (:id, 'jds-commerce', 'JDS Commerce')"), {"id": application_id})
        connection.execute(text("INSERT INTO auth_roles (id, application_id, key, name) VALUES (:id, :app, 'staff', 'Staff')"), {"id": role_id, "app": application_id})
        membership_id = uuid4()
        connection.execute(text("INSERT INTO jds_users (id, primary_email, display_name) VALUES (:id, :email, 'Staff')"), {"id": user_id, "email": f"{user_id}@staff.invalid"})
        connection.execute(text("INSERT INTO organization_memberships (id, organization_id, application_id, user_id, role_id, status, joined_at) VALUES (:id, :org, :app, :user, :role, 'active', now())"), {"id": membership_id, "org": organization_id, "app": application_id, "user": user_id, "role": role_id})
        connection.execute(text("INSERT INTO staff_pin_credentials (user_id, verifier, changed_at) VALUES (:user, 'verifier', now())"), {"user": user_id})
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT membership_id FROM staff_pin_credentials WHERE user_id = :user"), {"user": user_id}) == membership_id

    with engine.begin() as connection:
        tenant_b = uuid4()
        membership_b = uuid4()
        connection.execute(text("INSERT INTO organizations (id, slug, name) VALUES (:id, 'auth-tenant-b', 'Auth Tenant B')"), {"id": tenant_b})
        connection.execute(text("INSERT INTO organization_memberships (id, organization_id, application_id, user_id, role_id, status, joined_at) VALUES (:id, :org, :app, :user, :role, 'active', now())"), {"id": membership_b, "org": tenant_b, "app": application_id, "user": user_id, "role": role_id})
        connection.execute(text("INSERT INTO staff_pin_credentials (membership_id, user_id, verifier, changed_at) VALUES (:membership, :user, 'other', now())"), {"membership": membership_b, "user": user_id})
    with pytest.raises(SQLAlchemyError, match="cannot safely downgrade multi-membership staff PIN credentials"):
        command.downgrade(config, "20260820_23")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM staff_pin_credentials WHERE membership_id = :id"), {"id": membership_b})
        connection.execute(text("DELETE FROM organization_memberships WHERE id = :id"), {"id": membership_b})
        connection.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": tenant_b})
    command.downgrade(config, "20260820_23")
    engine.dispose()
    command.upgrade(config, "head")


@pytest.mark.postgresql
def test_clover_tenant_migration_backfills_tokens_and_refuses_unsafe_downgrade(
    postgresql_url: str,
) -> None:
    config = make_alembic_config(postgresql_url)
    command.downgrade(config, "base")
    command.upgrade(config, "20260821_24")
    engine = create_engine(postgresql_url)
    encrypted_access = "encrypted-access-material"
    encrypted_refresh = "encrypted-refresh-material"
    with engine.begin() as connection:
        ladels_id = connection.scalar(
            text("SELECT id FROM organizations WHERE slug = 'the-guest-house'")
        )
        connection.execute(
            text(
                "INSERT INTO clover_installations "
                "(merchant_id, environment, app_id, access_token_encrypted, "
                "refresh_token_encrypted, access_token_expires_at, connection_state) "
                "VALUES ('historical-merchant', 'sandbox', 'historical-app', "
                ":access, :refresh, now() + interval '1 hour', 'connected')"
            ),
            {"access": encrypted_access, "refresh": encrypted_refresh},
        )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT organization_id, id, access_token_encrypted, "
                "refresh_token_encrypted FROM clover_installations "
                "WHERE merchant_id = 'historical-merchant'"
            )
        ).mappings().one()
        assert row["organization_id"] == ladels_id
        assert row["id"] is not None
        assert row["access_token_encrypted"] == encrypted_access
        assert row["refresh_token_encrypted"] == encrypted_refresh
        assert MigrationContext.configure(connection).get_current_revision() == "20260822_25"

    with engine.begin() as connection:
        tenant_b = uuid4()
        connection.execute(
            text(
                "INSERT INTO organizations (id, slug, name) "
                "VALUES (:id, 'clover-tenant-b', 'Clover Tenant B')"
            ),
            {"id": tenant_b},
        )
        connection.execute(
            text(
                "INSERT INTO clover_installations "
                "(id, organization_id, merchant_id, environment, app_id, "
                "access_token_encrypted, refresh_token_encrypted, "
                "access_token_expires_at, connection_state) VALUES "
                "(:id, :organization_id, 'tenant-b-merchant', 'sandbox', "
                "'historical-app', 'b-access', 'b-refresh', "
                "now() + interval '1 hour', 'connected')"
            ),
            {"id": uuid4(), "organization_id": tenant_b},
        )
    with pytest.raises(
        SQLAlchemyError,
        match="cannot safely downgrade multi-tenant Clover installations",
    ):
        command.downgrade(config, "20260821_24")
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM clover_installations WHERE organization_id = :id"),
            {"id": tenant_b},
        )
        connection.execute(
            text("DELETE FROM organizations WHERE id = :id"), {"id": tenant_b}
        )
    command.downgrade(config, "20260821_24")
    engine.dispose()
    command.upgrade(config, "head")
@pytest.mark.postgresql
def test_migration_bootstrap_adopts_existing_catalog_without_data_loss(
    postgresql_url: str,
) -> None:
    config = make_alembic_config(postgresql_url)
    command.downgrade(config, "base")
    command.upgrade(config, "20260727_01")

    engine = create_engine(postgresql_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO categories "
                    "(slug, name, is_published, sort_order) "
                    "VALUES ('existing-category', 'Existing Category', true, 0)"
                )
            )
            connection.execute(text("DROP TABLE alembic_version"))

        migrate_database(postgresql_url)

        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert context.get_current_revision() == "20260822_25"
            assert connection.scalar(
                text(
                    "SELECT name FROM categories "
                    "WHERE slug = 'existing-category'"
                )
            ) == "Existing Category"
    finally:
        engine.dispose()


@pytest.mark.postgresql
def test_migration_bootstrap_reconciles_catalog_and_orders_without_data_loss(
    postgresql_url: str,
) -> None:
    config = make_alembic_config(postgresql_url)
    command.downgrade(config, "base")
    command.upgrade(config, "20260728_03")

    engine = create_engine(postgresql_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO categories "
                    "(slug, name, is_published, sort_order) "
                    "VALUES ('legacy-category', 'Legacy Category', true, 0)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO orders "
                    "(idempotency_key, request_fingerprint, public_access_token, "
                    "status, guest_name, guest_email, guest_phone, "
                    "requested_pickup_at, business_timezone, currency, "
                    "subtotal_cents, tax_cents, total_cents, version, expires_at) "
                    "VALUES ('legacy-order-key', :fingerprint, 'legacy-token', "
                    "'pending', 'Legacy Guest', 'legacy@example.com', "
                    "'+15555550100', now(), 'America/Toronto', 'USD', "
                    "1250, 0, 1250, 1, now() + interval '1 hour')"
                ),
                {"fingerprint": "a" * 64},
            )
            connection.execute(
                text(
                    "DROP TABLE product_availability_overrides, "
                    "product_availability, business_closures, business_hours, "
                    "business_settings"
                )
            )
            connection.execute(text("DROP TABLE alembic_version"))

        migrate_database(postgresql_url)

        inspector = inspect(engine)
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert context.get_current_revision() == "20260822_25"
            assert connection.scalar(
                text(
                    "SELECT guest_name FROM orders "
                    "WHERE idempotency_key = 'legacy-order-key'"
                )
            ) == "Legacy Guest"
            assert connection.scalar(
                text(
                    "SELECT name FROM categories "
                    "WHERE slug = 'legacy-category'"
                )
            ) == "Legacy Category"

        assert {
            "business_settings",
            "business_hours",
            "business_closures",
            "product_availability",
            "product_availability_overrides",
            "clover_installations",
        }.issubset(inspector.get_table_names())
        assert {
            "clover_merchant_id",
            "clover_checkout_session_id",
            "clover_checkout_url",
            "clover_checkout_expires_at",
        }.issubset(
            column["name"] for column in inspector.get_columns("orders")
        )
    finally:
        engine.dispose()


@pytest.mark.postgresql
@pytest.mark.parametrize("interrupted_revision", ["20260727_01", "20260728_02"])
def test_migration_bootstrap_resumes_interrupted_order_reconciliation(
    postgresql_url: str,
    interrupted_revision: str,
) -> None:
    config = make_alembic_config(postgresql_url)
    command.downgrade(config, "base")
    command.upgrade(config, "20260728_03")

    engine = create_engine(postgresql_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO orders "
                    "(idempotency_key, request_fingerprint, public_access_token, "
                    "status, guest_name, guest_email, guest_phone, "
                    "requested_pickup_at, business_timezone, currency, "
                    "subtotal_cents, tax_cents, total_cents, version, expires_at) "
                    "VALUES ('resume-order-key', :fingerprint, 'resume-token', "
                    "'pending', 'Resume Guest', 'resume@example.com', "
                    "'+15555550101', now(), 'America/Toronto', 'USD', "
                    "1250, 0, 1250, 1, now() + interval '1 hour')"
                ),
                {"fingerprint": "b" * 64},
            )
            connection.execute(text("DROP TABLE alembic_version"))

        if interrupted_revision == "20260727_01":
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "DROP TABLE product_availability_overrides, "
                        "product_availability, business_closures, business_hours, "
                        "business_settings"
                    )
                )
            command.stamp(config, "20260727_01")
        else:
            command.stamp(config, "20260728_02")

        migrate_database(postgresql_url)

        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert context.get_current_revision() == "20260822_25"
            assert connection.scalar(
                text(
                    "SELECT guest_name FROM orders "
                    "WHERE idempotency_key = 'resume-order-key'"
                )
            ) == "Resume Guest"
    finally:
        engine.dispose()


@pytest.mark.postgresql
def test_migration_bootstrap_refuses_partial_unversioned_schema(
    postgresql_url: str,
) -> None:
    config = make_alembic_config(postgresql_url)
    command.downgrade(config, "base")
    engine = create_engine(postgresql_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE categories (id bigint PRIMARY KEY)"))

        with pytest.raises(MigrationBootstrapError, match="partial set"):
            migrate_database(postgresql_url)

        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "categories",
        }
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE categories CASCADE"))
        engine.dispose()
        command.upgrade(config, "head")
