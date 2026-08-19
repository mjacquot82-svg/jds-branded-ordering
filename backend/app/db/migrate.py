import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import Table

from app.availability import models as availability_models  # noqa: F401
from app.catalog import models as catalog_models  # noqa: F401
from app.db.base import Base
from app.orders import models as order_models  # noqa: F401
from app.jds_auth import models as auth_models  # noqa: F401
from app.customers import models as customer_models  # noqa: F401
from app.push import models as push_models  # noqa: F401
from app.clover import models as clover_models  # noqa: F401

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CATALOG_BASELINE_REVISION = "20260727_01"
AVAILABILITY_BASELINE_REVISION = "20260728_02"
ORDER_BASELINE_REVISION = "20260728_03"
CATALOG_TABLE_NAMES = frozenset(
    {
        "categories",
        "products",
        "product_variants",
        "modifier_groups",
        "modifier_options",
        "product_modifier_groups",
    }
)
CATALOG_HEAD_ONLY_COLUMN_NAMES = frozenset({"is_lunch_special"})
MODIFIER_GROUP_HEAD_ONLY_COLUMN_NAMES = frozenset({"allow_quantity"})
AVAILABILITY_TABLE_NAMES = frozenset(
    {
        "business_settings",
        "business_hours",
        "business_closures",
        "product_availability",
        "product_availability_overrides",
    }
)
ORDER_TABLE_NAMES = frozenset(
    {
        "orders",
        "order_items",
        "order_item_modifiers",
    }
)
CLOVER_TABLE_NAMES = frozenset(
    {
        "clover_installations",
        "clover_payment_events",
    }
)
LEGACY_CATALOG_AND_ORDER_TABLE_NAMES = CATALOG_TABLE_NAMES | ORDER_TABLE_NAMES
LATER_MANAGED_TABLE_NAMES = (
    AVAILABILITY_TABLE_NAMES | ORDER_TABLE_NAMES | CLOVER_TABLE_NAMES
)
MANAGED_TABLE_NAMES = CATALOG_TABLE_NAMES | LATER_MANAGED_TABLE_NAMES
ORDER_CLOVER_COLUMN_NAMES = frozenset(
    {
        "clover_merchant_id",
        "clover_checkout_session_id",
        "clover_checkout_url",
        "clover_checkout_expires_at",
        "customer_user_id",
        "tax_name",
        "tax_rate_millionths",
        "fulfillment_status",
        "fulfillment_updated_at",
        "preparing_at",
        "ready_at",
        "completed_at",
        "cancelled_at",
    }
)
ORDER_HEAD_ONLY_CHECK_NAMES = frozenset(
    {
        "ck_orders_status_valid",
        "ck_orders_clover_checkout_consistent",
        "ck_orders_tax_name_nonblank",
        "ck_orders_tax_rate_millionths_valid",
        "ck_orders_fulfillment_status_valid",
    }
)
ORDER_ITEM_MODIFIER_HEAD_ONLY_COLUMN_NAMES = frozenset({"quantity"})
ORDER_ITEM_MODIFIER_HEAD_ONLY_CHECK_NAMES = frozenset(
    {"ck_order_item_modifiers_quantity_positive"}
)
AVAILABILITY_HEAD_ONLY_COLUMN_NAMES = frozenset(
    {"tax_name", "tax_rate_millionths", "ordering_mode"}
)
AVAILABILITY_HEAD_ONLY_CHECK_NAMES = frozenset(
    {
        "ck_business_settings_tax_name_nonblank",
        "ck_business_settings_tax_rate_millionths_valid",
        "ck_business_settings_ordering_mode_valid",
    }
)
AVAILABILITY_CLOSURE_HEAD_ONLY_COLUMN_NAMES = frozenset({"reopens_on"})
AVAILABILITY_CLOSURE_HEAD_ONLY_CHECK_NAMES = frozenset(
    {"ck_business_closures_reopens_after_start"}
)
MIGRATION_LOCK_NAME = "guesthouse_preorder_alembic"
TENANT_HEAD_ONLY_COLUMN_NAMES = frozenset({"organization_id"})
AVAILABILITY_BASELINE_TYPE_SIGNATURES = {
    ("business_settings", "id"): "SMALLINT",
    ("business_hours", "business_settings_id"): "SMALLINT",
    ("business_closures", "business_settings_id"): "SMALLINT",
}
CATALOG_BASELINE_UNIQUE_CONSTRAINTS = {
    "categories": {"uq_categories_slug": ("slug",)},
    "products": {"uq_products_slug": ("slug",)},
    "modifier_groups": {"uq_modifier_groups_key": ("key",)},
}
AVAILABILITY_BASELINE_UNIQUE_CONSTRAINTS = {
    "business_hours": {
        "uq_business_hours_settings_weekday": ("business_settings_id", "weekday")
    },
    "business_closures": {
        "uq_business_closures_settings_date": (
            "business_settings_id",
            "business_date",
        )
    },
    "product_availability_overrides": {
        "uq_product_availability_overrides_product_date": (
            "product_id",
            "business_date",
        )
    },
}
AVAILABILITY_BASELINE_FOREIGN_KEYS = {
    "business_hours": {
        "fk_business_hours_business_settings_id_business_settings": (
            ("business_settings_id",),
            "business_settings",
            ("id",),
            "CASCADE",
        )
    },
    "business_closures": {
        "fk_business_closures_business_settings_id_business_settings": (
            ("business_settings_id",),
            "business_settings",
            ("id",),
            "CASCADE",
        )
    },
    "product_availability": {
        "fk_product_availability_product_id_products": (
            ("product_id",),
            "products",
            ("id",),
            "CASCADE",
        )
    },
    "product_availability_overrides": {
        "fk_product_availability_overrides_product_id_products": (
            ("product_id",),
            "products",
            ("id",),
            "CASCADE",
        )
    },
}


class MigrationBootstrapError(RuntimeError):
    pass


def _alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _type_signature(column_type: object, engine: Engine) -> str:
    return " ".join(str(column_type.compile(dialect=engine.dialect)).upper().split())


def _expected_check_names(table: Table) -> set[str]:
    prefix = f"ck_{table.name}_"
    return {
        (
            str(constraint.name)
            if str(constraint.name).startswith(prefix)
            else f"{prefix}{constraint.name}"
        )
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name is not None
    }


def _validate_table(
    engine: Engine,
    table_name: str,
    *,
    excluded_column_names: frozenset[str] = frozenset(),
    excluded_check_names: frozenset[str] = frozenset(),
    additional_check_names: frozenset[str] = frozenset(),
    additional_unique_constraints: dict[str, tuple[str, ...]] | None = None,
    additional_foreign_keys: dict[
        str, tuple[tuple[str, ...], str, tuple[str, ...], str | None]
    ]
    | None = None,
    expected_type_signatures: dict[tuple[str, str], str] | None = None,
) -> list[str]:
    inspector = inspect(engine)
    expected = Base.metadata.tables[table_name]
    problems: list[str] = []

    actual_columns = {
        column["name"]: column for column in inspector.get_columns(table_name)
    }
    expected_columns = {
        column.name: column
        for column in expected.columns
        if column.name not in excluded_column_names
    }
    if set(actual_columns) != set(expected_columns):
        problems.append(
            f"{table_name} columns are {sorted(actual_columns)}; expected "
            f"{sorted(expected_columns)}"
        )
    for column_name in sorted(set(actual_columns) & set(expected_columns)):
        actual_column = actual_columns[column_name]
        expected_column = expected_columns[column_name]
        actual_type = _type_signature(actual_column["type"], engine)
        expected_type = (expected_type_signatures or {}).get(
            (table_name, column_name),
            _type_signature(expected_column.type, engine),
        )
        if actual_type != expected_type:
            problems.append(
                f"{table_name}.{column_name} type is {actual_type}; "
                f"expected {expected_type}"
            )
        if bool(actual_column["nullable"]) != bool(expected_column.nullable):
            problems.append(
                f"{table_name}.{column_name} nullable is "
                f"{actual_column['nullable']}; expected {expected_column.nullable}"
            )

    actual_primary_key = inspector.get_pk_constraint(table_name)
    expected_primary_key = expected.primary_key
    if (
        actual_primary_key.get("name") != expected_primary_key.name
        or list(actual_primary_key.get("constrained_columns") or [])
        != [column.name for column in expected_primary_key.columns]
    ):
        problems.append(f"{table_name} primary key does not match the baseline")

    actual_unique = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    }
    expected_unique = {
        str(constraint.name): tuple(column.name for column in constraint.columns)
        for constraint in expected.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name is not None
        and not {
            column.name for column in constraint.columns
        } & excluded_column_names
    }
    expected_unique.update(additional_unique_constraints or {})
    if actual_unique != expected_unique:
        problems.append(
            f"{table_name} unique constraints are {sorted(actual_unique)}; "
            f"expected {sorted(expected_unique)}"
        )

    actual_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints(table_name)
        if constraint.get("name")
    }
    expected_checks = (
        _expected_check_names(expected) - excluded_check_names
    ) | additional_check_names
    if actual_checks != expected_checks:
        problems.append(
            f"{table_name} check constraints are {sorted(actual_checks)}; "
            f"expected {sorted(expected_checks)}"
        )

    actual_foreign_keys = {
        constraint["name"]: (
            tuple(constraint["constrained_columns"]),
            constraint["referred_table"],
            tuple(constraint["referred_columns"]),
            (constraint.get("options") or {}).get("ondelete"),
        )
        for constraint in inspector.get_foreign_keys(table_name)
        if constraint.get("name")
    }
    expected_foreign_keys = {
        str(constraint.name): (
            tuple(element.parent.name for element in constraint.elements),
            constraint.elements[0].column.table.name,
            tuple(element.column.name for element in constraint.elements),
            constraint.ondelete,
        )
        for constraint in expected.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name is not None
        and not {
            element.parent.name for element in constraint.elements
        } & excluded_column_names
    }
    expected_foreign_keys.update(additional_foreign_keys or {})
    if actual_foreign_keys != expected_foreign_keys:
        problems.append(
            f"{table_name} foreign keys are {sorted(actual_foreign_keys)}; "
            f"expected {sorted(expected_foreign_keys)}"
        )

    actual_indexes = {
        index["name"]: (tuple(index["column_names"]), bool(index["unique"]))
        for index in inspector.get_indexes(table_name)
        if index.get("name") and not index.get("duplicates_constraint")
    }
    expected_indexes = {
        str(index.name): (
            tuple(column.name for column in index.columns),
            bool(index.unique),
        )
        for index in expected.indexes
        if index.name is not None
        and not {
            column.name for column in index.columns
        } & excluded_column_names
    }
    if actual_indexes != expected_indexes:
        problems.append(
            f"{table_name} indexes are {sorted(actual_indexes)}; "
            f"expected {sorted(expected_indexes)}"
        )

    return problems


def _validate_catalog_baseline(engine: Engine) -> None:
    problems = [
        problem
        for table_name in sorted(CATALOG_TABLE_NAMES)
        for problem in _validate_table(
            engine,
            table_name,
            excluded_column_names=(
                TENANT_HEAD_ONLY_COLUMN_NAMES | CATALOG_HEAD_ONLY_COLUMN_NAMES
                if table_name == "products"
                else TENANT_HEAD_ONLY_COLUMN_NAMES | MODIFIER_GROUP_HEAD_ONLY_COLUMN_NAMES
                if table_name == "modifier_groups"
                else TENANT_HEAD_ONLY_COLUMN_NAMES
                if table_name == "categories"
                else frozenset()
            ),
            additional_unique_constraints=CATALOG_BASELINE_UNIQUE_CONSTRAINTS.get(
                table_name
            ),
        )
    ]
    if problems:
        formatted = "\n- ".join(problems)
        raise MigrationBootstrapError(
            "Existing catalog schema cannot be safely adopted as Alembic "
            f"revision {CATALOG_BASELINE_REVISION}:\n- {formatted}"
        )


def _validate_order_baseline(engine: Engine) -> None:
    problems = _validate_table(
        engine,
        "orders",
        excluded_column_names=ORDER_CLOVER_COLUMN_NAMES,
        excluded_check_names=ORDER_HEAD_ONLY_CHECK_NAMES,
        additional_check_names=frozenset({"ck_orders_status_pending"}),
    )
    problems.extend(
        problem
        for table_name in sorted(ORDER_TABLE_NAMES - {"orders"})
        for problem in _validate_table(
            engine,
            table_name,
            excluded_column_names=(
                ORDER_ITEM_MODIFIER_HEAD_ONLY_COLUMN_NAMES
                if table_name == "order_item_modifiers"
                else frozenset()
            ),
            excluded_check_names=(
                ORDER_ITEM_MODIFIER_HEAD_ONLY_CHECK_NAMES
                if table_name == "order_item_modifiers"
                else frozenset()
            ),
        )
    )
    if problems:
        formatted = "\n- ".join(problems)
        raise MigrationBootstrapError(
            "Existing order schema cannot be safely adopted as Alembic "
            f"revision {ORDER_BASELINE_REVISION}:\n- {formatted}"
        )


def _validate_availability_baseline(engine: Engine) -> None:
    problems = [
        problem
        for table_name in sorted(AVAILABILITY_TABLE_NAMES)
        for problem in _validate_table(
            engine,
            table_name,
            excluded_column_names=(
                TENANT_HEAD_ONLY_COLUMN_NAMES | AVAILABILITY_HEAD_ONLY_COLUMN_NAMES
                if table_name == "business_settings"
                else TENANT_HEAD_ONLY_COLUMN_NAMES
                | AVAILABILITY_CLOSURE_HEAD_ONLY_COLUMN_NAMES
                if table_name == "business_closures"
                else TENANT_HEAD_ONLY_COLUMN_NAMES
            ),
            excluded_check_names=(
                AVAILABILITY_HEAD_ONLY_CHECK_NAMES
                if table_name == "business_settings"
                else AVAILABILITY_CLOSURE_HEAD_ONLY_CHECK_NAMES
                if table_name == "business_closures"
                else frozenset()
            ),
            additional_check_names=(
                frozenset({"ck_business_settings_singleton"})
                if table_name == "business_settings"
                else frozenset()
            ),
            additional_unique_constraints=AVAILABILITY_BASELINE_UNIQUE_CONSTRAINTS.get(
                table_name
            ),
            additional_foreign_keys=AVAILABILITY_BASELINE_FOREIGN_KEYS.get(table_name),
            expected_type_signatures=AVAILABILITY_BASELINE_TYPE_SIGNATURES,
        )
    ]
    if problems:
        formatted = "\n- ".join(problems)
        raise MigrationBootstrapError(
            "Existing availability schema cannot be safely adopted as Alembic "
            f"revision {AVAILABILITY_BASELINE_REVISION}:\n- {formatted}"
        )


def _adopt_catalog_and_order_baselines(engine: Engine, config: Config) -> None:
    _validate_catalog_baseline(engine)
    _validate_order_baseline(engine)
    print(
        "Existing catalog and order schemas match Alembic revisions "
        f"{CATALOG_BASELINE_REVISION} and {ORDER_BASELINE_REVISION}."
    )
    command.stamp(config, CATALOG_BASELINE_REVISION)
    command.upgrade(config, AVAILABILITY_BASELINE_REVISION)
    command.stamp(config, ORDER_BASELINE_REVISION)
    command.upgrade(config, "head")
    print(
        "Missing availability tables created; existing catalog and order data "
        "preserved; Alembic is at head."
    )


def _resume_catalog_and_order_adoption(
    engine: Engine,
    config: Config,
    revision: str,
    existing_managed_tables: set[str],
) -> bool:
    if (
        revision == CATALOG_BASELINE_REVISION
        and existing_managed_tables == LEGACY_CATALOG_AND_ORDER_TABLE_NAMES
    ):
        _validate_catalog_baseline(engine)
        _validate_order_baseline(engine)
        command.upgrade(config, AVAILABILITY_BASELINE_REVISION)
        command.stamp(config, ORDER_BASELINE_REVISION)
        command.upgrade(config, "head")
        print("Interrupted legacy-schema reconciliation resumed from revision 1.")
        return True

    expected_revision_2_tables = (
        LEGACY_CATALOG_AND_ORDER_TABLE_NAMES | AVAILABILITY_TABLE_NAMES
    )
    if (
        revision == AVAILABILITY_BASELINE_REVISION
        and existing_managed_tables == expected_revision_2_tables
    ):
        _validate_catalog_baseline(engine)
        _validate_availability_baseline(engine)
        _validate_order_baseline(engine)
        command.stamp(config, ORDER_BASELINE_REVISION)
        command.upgrade(config, "head")
        print("Interrupted legacy-schema reconciliation resumed from revision 2.")
        return True

    return False


def _current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def migrate_database(database_url: str | None = None) -> None:
    resolved_database_url = database_url or os.getenv("DATABASE_URL")
    if not resolved_database_url:
        raise MigrationBootstrapError("DATABASE_URL is required.")

    config = _alembic_config(resolved_database_url)
    engine = create_engine(resolved_database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT pg_advisory_lock(hashtext(:name))"),
                {"name": MIGRATION_LOCK_NAME},
            )
            try:
                revision = _current_revision(connection)
                existing_tables = set(inspect(connection).get_table_names())
                existing_managed_tables = existing_tables & MANAGED_TABLE_NAMES
                if revision is not None:
                    if _resume_catalog_and_order_adoption(
                        engine, config, revision, existing_managed_tables
                    ):
                        return
                    print(f"Alembic revision {revision} found; upgrading to head.")
                    command.upgrade(config, "head")
                    return

                if not existing_managed_tables:
                    print("No managed tables found; creating schema from Alembic.")
                    command.upgrade(config, "head")
                    return

                if existing_managed_tables == LEGACY_CATALOG_AND_ORDER_TABLE_NAMES:
                    _adopt_catalog_and_order_baselines(engine, config)
                    return

                if existing_managed_tables != CATALOG_TABLE_NAMES:
                    raise MigrationBootstrapError(
                        "Database has no Alembic revision and contains an "
                        "unsupported partial set of managed tables: "
                        f"{sorted(existing_managed_tables)}. No schema changes "
                        "were made."
                    )

                _validate_catalog_baseline(engine)
                print(
                    "Existing catalog schema matches Alembic revision "
                    f"{CATALOG_BASELINE_REVISION}; stamping baseline."
                )
                command.stamp(config, CATALOG_BASELINE_REVISION)
                command.upgrade(config, "head")
                print("Existing catalog data preserved; Alembic is at head.")
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:name))"),
                    {"name": MIGRATION_LOCK_NAME},
                )
    finally:
        engine.dispose()


def main() -> None:
    migrate_database()


if __name__ == "__main__":
    main()
